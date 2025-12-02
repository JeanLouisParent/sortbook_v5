# SortBook v5 - Automated Book Processing Pipeline

Ce projet fournit un pipeline ETL (Extract, Transform, Load) pour traiter, enrichir et organiser une bibliothèque de livres numériques au format EPUB.

Il est architecturé autour d'une application Python principale et de services conteneurisés (n8n) exposés via un reverse proxy Traefik.

## Table des matières

-   [Architecture](#architecture)
-   [Installation](#installation)
-   [Utilisation](#utilisation)
-   [Développement](#développement)

## Architecture

L'architecture est conçue pour être modulaire et extensible.

-   **Application Python (`src/`)**: Un outil en ligne de commande qui orchestre le traitement de chaque livre. Il extrait les métadonnées, appelle des services externes pour les enrichir, et stocke le résultat dans une base de données PostgreSQL.
-   **n8n**: Un service d'automatisation de workflows, utilisé ici pour créer des micro-services d'enrichissement de données (ex: recherche d'informations sur un livre à partir de son ISBN).
-   **PostgreSQL**: La base de données qui stocke l'état et les métadonnées de tous les livres traités.
-   **Traefik**: Le reverse proxy qui expose le service n8n de manière sécurisée.
-   **Redis**: Un gestionnaire d'état optionnel pour assurer la reprise du traitement sans traiter deux fois le même fichier.

Pour une description plus détaillée, consultez le document d'[architecture](./doc/architecture.md).

## Installation

### Prérequis

-   Docker & Docker Compose
-   Python 3.10+
-   Une instance de Traefik fonctionnelle (ex: via le projet `docker-toolkit`).
-   Une base de données PostgreSQL accessible.

### Étapes

1.  **Cloner le projet**

    ```bash
    git clone <repository_url>
    cd sortbook_v5
    ```

2.  **Configuration de l'application**

    Créez un fichier `.env` à la racine du dossier `src/` en vous basant sur `src/.env.example`. Remplissez les informations de connexion à la base de données, Redis, et les URLs de vos services.

    ```bash
    cp src/.env.example src/.env
    # Éditez src/.env avec vos informations
    ```

3.  **Configuration de n8n**

    Créez un fichier `.env` dans le dossier `n8n/`.

    ```bash
    cp n8n/.env.example n8n/.env
    # Éditez n8n/.env
    ```

4.  **Installer les dépendances Python**

    ```bash
    pip install -r requirements.txt
    ```

## Utilisation

Pour un guide d'utilisation complet, référez-vous au fichier [USAGE.md](./USAGE.md).

### 1. Démarrer les services Docker

Assurez-vous que votre instance Traefik est démarrée. Ensuite, lancez n8n :

```bash
docker compose up -d
```

### 2. Initialiser la base de données

Cette commande exécute le `schema.sql` pour créer les tables nécessaires.

```bash
python scripts/init_db.py
```

### 3. Lancer le pipeline de traitement

Pour traiter les nouveaux livres présents dans le dossier que vous avez configuré :

```bash
python src/main.py run --use-redis
```

Les options de cette commande utilisent désormais les valeurs définies dans `config/config.yaml` (section `commands.run`) comme comportements par défaut. Modifier ce fichier vous permet d'ajuster, par exemple, l'activation de Redis ou la limite de fichiers sans avoir à répéter les options en ligne de commande. Toute option passée à `python src/main.py run` continue de surcharger ces valeurs par défaut.

## Développement

### Structure du projet

```
/
├── data/               # Données persistantes des conteneurs (ex: n8n)
├── database/           # Schéma SQL
├── doc/                # Documentation (architecture, etc.)
├── n8n/                # Configuration du service n8n
├── scripts/            # Scripts utilitaires (init_db.py)
├── src/                # Code source de l'application Python
├── docker-compose.yml  # Composition des services Docker
├── requirements.txt    # Dépendances Python
└── README.md           # Ce fichier
```

### Lancer les tests

Ce projet a été configuré sans suite de tests formelle à la demande de l'utilisateur.

### Linter et Formatter

Pour assurer une qualité de code constante, vous pouvez utiliser des outils comme `black` et `ruff`.

```bash
# Exemple avec ruff
ruff check .
ruff format .
```
