# Architecture du Projet

Ce document décrit l'architecture globale du projet `sortbook_v5`, ses composants principaux et leurs interactions.

## Vue d'ensemble

Le projet est conçu comme un pipeline de traitement de données ETL (Extract, Transform, Load) destiné à organiser une bibliothèque de livres numériques au format EPUB.

L'architecture repose sur plusieurs services conteneurisés avec Docker et un script principal en Python pour l'orchestration.

## Composants Principaux

![Diagramme d'architecture simplifié](https://placehold.co/800x400?text=Diagramme+d'architecture)
*(Un diagramme réel montrerait les flux de données entre les composants)*

### 1. Application Python (`src/`)

C'est le cœur du système. Un script en ligne de commande (`src/main.py`) orchestre le pipeline de traitement pour chaque livre.

-   **Structure** : Le code est organisé dans un package (`src`) avec une séparation claire des responsabilités :
    -   `main.py`: Interface CLI (Click) et orchestration de haut niveau.
    -   `core/`: Logique métier principale, incluant `pipeline.py` (définit les étapes de traitement) et `state.py` (gestion de l'état avec Redis).
    -   `tasks/`: Tâches atomiques du pipeline :
        -   `extract.py`: Fonctions pour extraire des informations directement depuis le fichier EPUB (métadonnées, ISBN, couverture, hash...).
        -   `integrate.py`: Clients HTTP pour communiquer avec des services externes (N8N, Flowise).
    -   `db/`: Logique d'accès à la base de données (via `asyncpg`).
    -   `config.py`: Gestion de la configuration via Pydantic, chargée depuis un fichier `.env`.

-   **Fonctionnement** : Le pipeline exécute les étapes suivantes pour chaque livre :
    1.  Calcul du hash du fichier.
    2.  Vérification de l'existence de ce hash en base de données pour éviter les doublons.
    3.  Extraction des métadonnées locales (titre, auteur, ISBN...).
    4.  Appel à des services externes (workflows N8N) pour enrichir les données via l'ISBN ou les métadonnées.
    5.  (Optionnel) Appel à des services d'IA (Flowise) pour des analyses plus complexes (validation, analyse de couverture).
    6.  Prise de décision pour choisir le titre et l'auteur finaux.
    7.  Mise à jour de l'entrée du livre en base de données avec le statut final (`processed`, `failed`, `duplicate_isbn`).

### 2. n8n (Service d'automatisation)

-   **Rôle** : Fournit des workflows pour enrichir les données. Ces workflows sont exposés via des webhooks et appelés par l'application Python.
-   **Exemples de workflows** :
    -   **Recherche par ISBN** : Prend un ISBN en entrée, interroge des APIs publiques (Google Books, OpenLibrary, etc.) et retourne une structure JSON standardisée avec le titre, l'auteur, la date de publication, etc.
    -   **Recherche par métadonnées** : Prend un titre et un auteur, effectue une recherche textuelle sur les mêmes APIs et retourne les meilleures correspondances.
-   **Déploiement** : Tourne dans un conteneur Docker et ses données sont persistées dans le dossier `data/n8n/`.

### 3. PostgreSQL (Base de données)

-   **Rôle** : Stocke toutes les informations relatives aux livres traités. C'est la source de vérité du système.
-   **Schéma (`database/schema.sql`)** : La table principale `books` contient :
    -   Les informations de base du fichier (nom, chemin, taille, hash).
    -   L'état du traitement (`pending`, `processed`, `failed`, `duplicate_hash`, `duplicate_isbn`).
    -   Toutes les données extraites et enrichies, souvent stockées dans des colonnes de type `JSONB` pour plus de flexibilité.
    -   Les données finales choisies (titre, auteur).
-   **Déploiement** : Il est supposé qu'une instance de PostgreSQL est disponible (par exemple, lancée via le `docker-toolkit`).

### 4. Redis (Gestionnaire d'état)

-   **Rôle** : Utilisé de manière optionnelle pour la reprise sur erreur.
-   **Fonctionnement** : Stocke l'identifiant (chemin de fichier) de chaque livre qui a été traité. Au démarrage d'un nouveau traitement, le script peut demander à Redis la liste des fichiers déjà traités pour les ignorer, évitant ainsi un travail redondant.

### 5. Traefik (Reverse Proxy)

-   **Rôle** : Expose de manière sécurisée les services web, notamment l'interface de **n8n**.
-   **Fonctionnement** : Route les requêtes basées sur le nom d'hôte (ex: `n8n.mondomaine.local`) vers le conteneur Docker approprié et gère automatiquement la génération de certificats SSL/TLS.
-   **Déploiement** : Externe à ce projet, typiquement fourni par `docker-toolkit`.
