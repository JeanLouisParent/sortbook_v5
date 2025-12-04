"""
Point d'entrée principal de l'application de traitement de livres.
Fournit une interface en ligne de commande (CLI) pour exécuter,
initialiser et interagir avec le pipeline.
"""
import asyncio
import logging
import sys
from itertools import islice
from pathlib import Path
from typing import Optional, Any, Dict, Iterator
import os
import shutil

# When executed directly (python src/main.py), ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click
import httpx
from asyncpg.pool import Pool

from src.config import settings
from src.logging_config import setup_logging
from src.db import database as db
from src.core import pipeline
from src.core.state import RedisStateManager

logger = logging.getLogger(__name__)
run_defaults = settings.commands.run
_RUN_TEST_FILE_DEFAULT = str(run_defaults.test_file) if run_defaults.test_file else None


def _purge_logs():
    logs_dir = PROJECT_ROOT / "logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*"):
            if log_file.is_file():
                log_file.unlink()


def _workflow_has_payload(entry: Optional[Dict[str, Any]]) -> bool:
    return bool(
        isinstance(entry, dict)
        and entry.get("success")
        and isinstance(entry.get("payload"), dict)
    )


def _format_file_line(
    filename: str,
    has_isbn: bool,
    has_metadata: bool,
    processed: bool,
    process_origin: str,
) -> str:
    def _label(value: bool) -> str:
        return "oui" if value else "non"

    origin = process_origin or "inconnu"
    return (
        f"{filename} | isbn={_label(has_isbn)} | metadata={_label(has_metadata)} | "
        f"traité={_label(processed)} | par={origin}"
    )


def _has_any_metadata(result: Dict[str, Any]) -> bool:
    if _workflow_has_payload(result.get("json_n8n_isbn")):
        return True
    if _workflow_has_payload(result.get("json_n8n_metadata")):
        return True
    extract_metadata = result.get("json_extract_metadata")
    metadata = extract_metadata.get("metadata") if isinstance(extract_metadata, dict) else None
    return bool(metadata)


def _iter_epub_files(base_dir: Path) -> Iterator[Path]:
    """Itère paresseusement les fichiers EPUB dans l'ordre trié."""
    if not base_dir.exists():
        return

    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames.sort()
        for filename in sorted(filenames):
            if filename.lower().endswith(".epub"):
                yield Path(dirpath) / filename

@click.group()
def cli():
    """Outil de traitement de livres EPUB."""
    pass



@cli.command("run")
@click.option(
    "--dry-run/--no-dry-run",
    default=run_defaults.dry_run,
    show_default=True,
    help="Affiche les résultats sans écrire en DB ni déplacer les fichiers.",
)
@click.option(
    "--test-file",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    default=_RUN_TEST_FILE_DEFAULT,
    show_default=_RUN_TEST_FILE_DEFAULT or False,
    help="Traite un seul fichier en mode test.",
)
@click.option(
    "--limit",
    default=run_defaults.limit,
    show_default=True,
    help="Nombre maximum de fichiers à traiter (0 pour tous).",
)
@click.option(
    "--offset",
    default=run_defaults.offset,
    show_default=True,
    help="Décalage dans la liste des fichiers à traiter.",
)
@click.option(
    "--use-redis/--no-use-redis",
    default=run_defaults.use_redis,
    show_default=True,
    help="Utilise Redis pour la gestion de l'état de la progression.",
)
@click.option(
    "-v",
    "--verbose/--no-verbose",
    default=run_defaults.verbose,
    show_default=True,
    help="Active l'affichage détaillé des logs en console.",
)
@click.option(
    "--reset/--no-reset",
    default=run_defaults.reset,
    show_default=True,
    help="Tronque la base de données et réinitialise l'état Redis avant de démarrer.",
)
@click.option(
    "--n8n-test/--no-n8n-test",
    default=run_defaults.n8n_test,
    show_default=True,
    help="Utilise les webhooks de test configurés pour N8N.",
)
def run_command(
    dry_run: bool,
    test_file: Optional[str],
    limit: int,
    offset: int,
    use_redis: bool,
    verbose: bool,
    reset: bool,
    n8n_test: bool,
):
    """Exécute le pipeline de traitement des fichiers EPUB."""
    if reset:
        _purge_logs()
    setup_logging(verbose)
    
    if dry_run:
        logger.info("Lancement en mode --dry-run. Aucune modification ne sera persistée.")

    test_mode = test_file is not None
    if test_mode:
        logger.info(f"Lancement en mode test sur un seul fichier: {test_file}")

    asyncio.run(
        main_process(
            dry_run=dry_run,
            test_file_path=Path(test_file) if test_file else None,
            limit=limit,
            offset=offset,
            use_redis_state=use_redis,
            reset=reset,
            use_n8n_test=n8n_test,
        )
    )

async def main_process(
    dry_run: bool,
    test_file_path: Optional[Path],
    limit: int,
    offset: int,
    use_redis_state: bool,
    reset: bool,
    use_n8n_test: bool,
):
    """Coroutine principale orchestrant le traitement."""
    pool: Optional[Pool] = None
    redis_manager = RedisStateManager(settings)

    try:
        if use_redis_state:
            await redis_manager.connect()

        # --- NEW RESET LOGIC ---
        if reset:
            logger.warning("Mode --reset activé : troncature de la base de données et réinitialisation de Redis.")
            await db.truncate_db(settings)
            if use_redis_state:
                await redis_manager.reset_state()
        # --- END NEW RESET LOGIC ---

        pool = await db.create_pool(settings)
        if not pool:
            logger.error("Échec de la création du pool de connexions DB. Arrêt.")
            return

        if test_file_path:
            files_to_process = [test_file_path]
        else:
            files_iter = _iter_epub_files(settings.epub_dir)
            if use_redis_state:
                files_iter = await redis_manager.filter_processed_files(files_iter)

            if offset > 0:
                files_iter = islice(files_iter, offset, None)

            if limit > 0:
                files_iter = islice(files_iter, limit)

            files_to_process = list(files_iter)

        if not files_to_process:
            logger.info("Aucun nouveau fichier à traiter.")
            return

        logger.info(f"{len(files_to_process)} fichier(s) à traiter.")

        results = []
        async with httpx.AsyncClient(timeout=settings.request_timeout, verify=settings.n8n_verify_ssl) as http_client:
            for file_path in files_to_process:
                try:
                    result = await pipeline.run_pipeline(
                        file_path,
                        pool,
                        settings,
                        dry_run=dry_run,
                        test_mode=test_file_path is not None,
                        use_n8n_test=use_n8n_test,
                        http_client=http_client,
                    )
                    results.append(result)
                except Exception as exc:  # Fallback en cas d'erreur inattendue
                    results.append(exc)

        printed_any = False
        for idx, result in enumerate(results):
            file_path = files_to_process[idx]
            file_name = file_path.name

            def _maybe_separator():
                nonlocal printed_any
                if printed_any:
                    logger.info("----", extra={"plain": True})
                else:
                    printed_any = True

            if isinstance(result, Exception):
                logger.error(f"Erreur non gérée pour {file_path}: {result}")
                _maybe_separator()
                logger.info(
                    _format_file_line(file_name, False, False, False, "exception"),
                    extra={"plain": True},
                )
                printed_any = True
                continue

            if not isinstance(result, dict):
                _maybe_separator()
                logger.info(
                    _format_file_line(file_name, False, False, False, "inconnu"),
                    extra={"plain": True},
                )
                printed_any = True
                continue

            status = result.get("status") or "unknown"

            if use_redis_state and status in ["processed", "failed", "duplicate_isbn"]:
                await redis_manager.add_processed_file(file_path)

            has_isbn = bool(result.get("isbn"))
            has_metadata = _has_any_metadata(result)
            processed_flag = status == "processed"
            process_origin = (result.get("choice_source") or "unknown") if processed_flag else status

            _maybe_separator()
            logger.info(
                _format_file_line(
                    file_name,
                    has_isbn,
                    has_metadata,
                    processed_flag,
                    process_origin or "inconnu",
                ),
                extra={"plain": True},
            )
            printed_any = True


    finally:
        if pool:
            await db.close_pool(pool)
        if redis_manager.redis_client:
            await redis_manager.close()

@cli.command("list-pending")
def list_pending():
    """Liste les fichiers marqués comme 'pending' dans la base de données."""
    setup_logging(verbose=False)
    
    async def _list_pending():
        pool = await db.create_pool(settings)
        if not pool:
            return
        
        try:
            pending_books = await db.get_pending_books(pool)
            if not pending_books:
                click.echo("Aucun livre en attente ('pending') dans la base de données.")
            else:
                click.echo(f"{len(pending_books)} livre(s) en attente:")
                for book in pending_books:
                    click.echo(f" - {book['file_path']}")
        finally:
            if pool:
                await db.close_pool(pool)

    asyncio.run(_list_pending())

if __name__ == "__main__":
    cli()
