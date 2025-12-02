"""
Gestion de l'état de la file de traitement avec Redis.
Permet la reprise du traitement en cas d'interruption.
"""
import logging
from typing import Optional, List, Set
from pathlib import Path

import redis.asyncio as redis

from src.config import Settings

logger = logging.getLogger(__name__)

class RedisStateManager:
    """
    Gère l'état du pipeline dans Redis pour la reprise.
    """
    def __init__(self, settings: Settings):
        self._settings = settings
        self.redis_client: Optional[redis.Redis] = None
        self._processed_key = "book_processor:processed_files"

    async def connect(self):
        """Initialise la connexion à Redis."""
        if not self._settings.redis_host:
            logger.warning("Hôte Redis non configuré. Le gestionnaire d'état Redis est désactivé.")
            return

        try:
            self.redis_client = redis.Redis(
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                db=self._settings.redis_db,
                decode_responses=True, # Important pour manipuler des strings
            )
            await self.redis_client.ping()
            logger.info("Connecté à Redis avec succès.")
        except redis.RedisError as e:
            logger.error(f"Impossible de se connecter à Redis: {e}. Le traitement continuera sans reprise possible.")
            self.redis_client = None

    async def close(self):
        """Ferme la connexion à Redis."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Connexion Redis fermée.")

    async def filter_processed_files(self, all_files: List[Path]) -> List[Path]:
        """
        Filtre une liste de fichiers pour ne garder que ceux qui n'ont pas encore été traités.
        """
        if not self.redis_client:
            return all_files

        try:
            processed_files_set: Set[str] = await self.redis_client.smembers(self._processed_key)
            if not processed_files_set:
                return all_files
            
            files_to_process = [
                file for file in all_files if str(file) not in processed_files_set
            ]
            
            logger.info(f"{len(all_files) - len(files_to_process)} fichiers déjà traités ignorés grâce à Redis.")
            return files_to_process

        except redis.RedisError as e:
            logger.error(f"Erreur Redis lors du filtrage des fichiers: {e}. Traitement de tous les fichiers.")
            return all_files

    async def add_processed_file(self, file_path: Path):
        """Marque un fichier comme traité dans Redis."""
        if not self.redis_client:
            return

        try:
            await self.redis_client.sadd(self._processed_key, str(file_path))
        except redis.RedisError as e:
            logger.error(f"Erreur Redis lors de l'ajout du fichier traité {file_path}: {e}")
    
    async def reset_state(self):
        """Réinitialise l'état des fichiers traités dans Redis."""
        if not self.redis_client:
            logger.warning("Impossible de réinitialiser: client Redis non disponible.")
            return
        
        try:
            await self.redis_client.delete(self._processed_key)
            logger.info("L'état de progression dans Redis a été réinitialisé.")
        except redis.RedisError as e:
            logger.error(f"Erreur Redis lors de la réinitialisation de l'état: {e}")
