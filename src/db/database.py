"""
Opérations et pool de connexions pour la base de données PostgreSQL avec asyncpg.
"""
import json
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

import asyncpg
from asyncpg.pool import Pool

from src.config import Settings

logger = logging.getLogger(__name__)
DB_SCHEMA = "book_data"
BOOK_UPDATE_COLUMNS = {
    "isbn",
    "isbn_source",
    "has_cover",
    "choice_source",
    "final_author",
    "final_title",
    "status",
    "processing_completed_at",
    "processing_time_ms",
    "error_message",
    "json_extract_isbn",
    "json_extract_metadata",
    "json_extract_cover",
    "json_n8n_response",
}

async def create_pool(settings: Settings) -> Optional[Pool]:
    """Crée un pool de connexions PostgreSQL."""
    try:
        pool = await asyncpg.create_pool(
            dsn=str(settings.postgres_dsn),
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("Pool de connexions PostgreSQL créé avec succès.")
        return pool
    except (asyncpg.PostgresError, OSError) as e:
        logger.error(f"Impossible de se connecter à PostgreSQL: {e}")
        return None

async def close_pool(pool: Pool):
    """Ferme le pool de connexions."""
    await pool.close()
    logger.info("Pool de connexions PostgreSQL fermé.")

async def init_db(settings: Settings):
    """Initialise la base de données en exécutant le script schema.sql."""
    try:
        conn = await asyncpg.connect(dsn=str(settings.postgres_dsn))
        with open("database/schema.sql", "r") as f:
            await conn.execute(f.read())
        await conn.close()
        logger.info("Base de données initialisée avec succès.")
    except (asyncpg.PostgresError, OSError, FileNotFoundError) as e:
        logger.error(f"Erreur lors de l'initialisation de la DB: {e}")
        raise

async def truncate_db(settings: Settings):
    """Tronque la base de données en supprimant et recréant le schéma."""
    try:
        conn = await asyncpg.connect(dsn=str(settings.postgres_dsn))
        # Supprime le schéma s'il existe
        await conn.execute(f"DROP SCHEMA IF EXISTS {DB_SCHEMA} CASCADE;")
        logger.info(f"Schéma '{DB_SCHEMA}' supprimé avec succès (s'il existait).")

        # Recrée le schéma
        with open("database/schema.sql", "r") as f:
            await conn.execute(f.read())
        await conn.close()
        logger.info("Base de données tronquée et réinitialisée avec schema.sql avec succès.")
    except (asyncpg.PostgresError, OSError, FileNotFoundError) as e:
        logger.error(f"Erreur lors de la troncation et réinitialisation de la base de données: {e}")
        raise

async def find_book_by_hash(pool: Pool, file_hash: str) -> Optional[Dict[str, Any]]:
    """Recherche un livre par son hash."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT id, status FROM {DB_SCHEMA}.books WHERE file_hash = $1", file_hash)
        return dict(row) if row else None

async def find_book_by_isbn(pool: Pool, isbn: str) -> Optional[Dict[str, Any]]:
    """Recherche un livre traité avec succès par son ISBN."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT id, status FROM {DB_SCHEMA}.books WHERE isbn = $1 AND status = 'processed'", isbn
        )
        return dict(row) if row else None

async def create_book_entry(
    pool: Pool,
    file_hash: str,
    filename: str,
    file_path: str,
    file_size: int,
) -> UUID:
    """Crée une nouvelle entrée pour un livre avec le statut 'pending'."""
    async with pool.acquire() as conn:
        book_id = await conn.fetchval(
            f"""
            INSERT INTO {DB_SCHEMA}.books (file_hash, filename, file_path, file_size, status, processing_started_at)
            VALUES ($1, $2, $3, $4, 'pending', NOW())
            RETURNING id
            """,
            file_hash,
            filename,
            file_path,
            file_size,
        )
        return book_id

async def update_book_entry(pool: Pool, book_id: UUID, data: Dict[str, Any]):
    """Met à jour une entrée de livre existante."""
    # Construit la requête de mise à jour dynamiquement
    set_clauses = []
    values = []
    for key, value in data.items():
        if key not in BOOK_UPDATE_COLUMNS:
            continue
        placeholder = len(values) + 2
        set_clauses.append(f"{key} = ${placeholder}")
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value))
        else:
            values.append(value)

    if not set_clauses:
        return
    
    query = f"UPDATE {DB_SCHEMA}.books SET {', '.join(set_clauses)} WHERE id = $1"
    
    async with pool.acquire() as conn:
        await conn.execute(query, book_id, *values)

async def get_pending_books(pool: Pool) -> List[Dict[str, Any]]:
    """Récupère les livres avec le statut 'pending'."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT file_path, status FROM {DB_SCHEMA}.books WHERE status = 'pending'")
        return [dict(row) for row in rows]
