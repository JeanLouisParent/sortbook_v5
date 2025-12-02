"""
Fonctions utilitaires partagées par différents modules du projet.
"""
import asyncio
import hashlib
from pathlib import Path
from typing import Callable, Any, Coroutine, TypeVar

T = TypeVar("T")

def calculate_file_hash(file_path: Path) -> str:
    """
    Calcule le hash SHA256 d'un fichier.

    Args:
        file_path: Le chemin vers le fichier.

    Returns:
        Le hash SHA256 du fichier en hexadécimal.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Lire le fichier par blocs pour ne pas surcharger la mémoire
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


async def retry_async[
    **P, T
](
    func: Callable[P, Coroutine[Any, Any, T]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """
    Tente de ré-exécuter une fonction asynchrone en cas d'échec.
    
    Cette fonction est un placeholder simple. Une implémentation plus robuste
    utiliserait une bibliothèque comme `tenacity`.
    """
    # TODO: Utiliser tenacity pour une meilleure gestion des re-essais
    # avec backoff exponentiel.
    max_retries = 3
    last_exception: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            await asyncio.sleep(1 * (attempt + 1))
    
    raise last_exception if last_exception else RuntimeError("Retry failed")
