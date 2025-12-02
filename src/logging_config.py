"""
Configuration centralisée du logging pour l'application.

Ce module met en place deux handlers :
- Un StreamHandler pour afficher les logs dans la console.
- Un RotatingFileHandler pour écrire les logs dans un fichier avec rotation.
"""
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "processing.log"


def setup_logging(verbose: bool = False):
    """
    Configure le logger racine.

    Args:
        verbose (bool): Si True, le niveau de log de la console est réglé sur DEBUG,
                        sinon sur INFO.
    """
    logging.basicConfig(
        level=logging.DEBUG,  # Niveau le plus bas pour capturer tous les messages
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            # Handler pour le fichier de log
            RotatingFileHandler(
                LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5
            )
        ],
    )

    # Créer un handler pour la console et le configurer
    console_handler = logging.StreamHandler(sys.stdout)
    console_log_level = logging.DEBUG if verbose else logging.INFO
    console_handler.setLevel(console_log_level)

    # Appliquer un formateur différent pour la console pour plus de lisibilité
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    # Ajouter le handler console au logger racine
    logging.getLogger().addHandler(console_handler)

    # Silence les loggers trop verbeux
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("ebooklib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
