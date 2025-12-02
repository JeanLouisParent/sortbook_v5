# Guide d'utilisation

Ce projet fournit les outils pour traiter une bibliothèque de livres numériques (EPUB) de manière automatisée.

## Prérequis

-   Docker & Docker Compose
-   Python 3.10+
-   Une instance de Traefik (proxy inverse) fonctionnelle, idéalement via le projet `docker-toolkit`.

## Installation

1.  **Clonez le projet**

    ```bash
    git clone <repository_url>
    cd <project_directory>
    ```

2.  **Configurez les services**

    -   **n8n** : Copiez `n8n/.env.example` vers `n8n/.env` et remplissez les variables.
    -   **book_processor** : Copiez `src/.env.example` vers `src/.env` et configurez les accès à la base de données, Redis, et les URLs des services externes (N8N, Flowise).

3.  **Installez les dépendances Python**

    ```bash
    pip install -r requirements.txt
    ```

## Lancement des services

1.  **Démarrez Traefik** (si ce n'est pas déjà fait)

    ```bash
    cd ~/docker-toolkit
    docker compose up -d
    ```

2.  **Démarrez n8n**

    ```bash
    docker compose up -d
    ```

    Le service n8n sera accessible via le nom d'hôte que vous avez configuré (ex: `https://n8n.votredomaine.local`).

## Utilisation du processeur de livres

L'outil principal est accessible via `src/main.py` et utilise `click` pour une interface en ligne de commande.

### 1. Initialiser la base de données

Avant la première utilisation, créez le schéma de la base de données :

```bash
python scripts/init_db.py
```

### 2. Lancer le traitement

Pour traiter tous les nouveaux livres dans le dossier configuré (`EPUB_DIR` dans votre `.env`) :

```bash
python src/main.py run
```

#### Options utiles

-   **Lancer un traitement à sec (`--dry-run`)** : Simule le traitement sans écrire en base de données ni appeler les APIs. Utile pour le débogage.

    ```bash
    python src/main.py run --dry-run
    ```

-   **Traiter un seul fichier (`--test-file`)** : Idéal pour tester le pipeline sur un livre spécifique.

    ```bash
    python src/main.py run --test-file /chemin/vers/mon/livre.epub
    ```

-   **Limiter le nombre de fichiers (`--limit`)** :

    ```bash
    python src/main.py run --limit 10 # Traite les 10 premiers fichiers
    ```

-   **Forcer l'utilisation des webhooks N8N de test (`--n8n-test`)** : Pratique pour valider vos workflows dans l'environnement de test défini dans `config/config.yaml`.

    ```bash
    python src/main.py run --n8n-test
    ```

-   **Utiliser Redis pour la reprise (`--use-redis`)** : Empêche de retraiter les fichiers qui ont déjà été traités lors d'exécutions précédentes.

    ```bash
    python src/main.py run --use-redis
    ```

### 3. Consulter l'état

Pour voir les livres qui sont en attente de traitement dans la base de données :

```bash
python src/main.py list-pending
```
