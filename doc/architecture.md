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
    6.  Prise de décision pour choisir le titre et l'auteur finaux uniquement à partir des workflows (`n8n_isbn`, `n8n_metadata`, Flowise…). Les métadonnées locales ne sont jamais utilisées comme fallback.
    7.  Mise à jour de l'entrée du livre en base de données avec le statut final (`processed`, `failed`, `duplicate_isbn`).

-   **Exécution** :
    -   Les EPUB sont traités séquentiellement afin de simplifier le suivi et la reprise.
    -   L'option `--dry-run` exécute toutes les étapes (écriture en base, mise à jour Redis, appels externes) et n'évite que les déplacements de fichiers.
    -   `--reset` réinitialise toujours le schéma PostgreSQL et l'état Redis, puis purge le dossier `logs/` avant d'initialiser le logging.
    -   La console affiche une seule ligne par fichier, tandis que `logs/processing.log` conserve l'intégralité des détails (requêtes HTTP, erreurs, etc.).

### 2. n8n (Service d'automatisation)

-   **Rôle** : Fournit des workflows pour enrichir les données. Ces workflows sont exposés via des webhooks et appelés par l'application Python.
-   **Exemples de workflows** :
    -   **Recherche par ISBN** : Prend un ISBN en entrée, interroge des APIs publiques (Google Books, OpenLibrary, etc.) et retourne une structure JSON standardisée avec le titre, l'auteur, la date de publication, etc.
    -   **Recherche par métadonnées** : Prend un titre et un auteur, effectue une recherche textuelle sur les mêmes APIs et retourne les meilleures correspondances.
-   **Schéma de réponse attendu** : Chaque workflow (N8N ou Flowise) doit renvoyer un JSON respectant la structure suivante, afin d'être consommé correctement par `src/main.py` :

    ```json
    {
      "success": true,
      "source": "n8n_isbn",              // identifie le workflow (n8n_isbn, n8n_metadata, flowise_check, flowise_cover…)
      "payload": {
        "title": "Titre proposé",
        "author": "Auteur proposé",
        "language": "fr",                // champs additionnels optionnels
        "publisher": "Maison d'édition",
        "published_at": "2020-05-01",
        "confidence": 0.82,              // score facultatif (0-1)
        "extra": { ... }                 // zone libre pour des données spécifiques au workflow
      },
      "errors": [],                      // liste de messages en cas d'échec
      "raw": { ... }                     // réponse brute éventuelle pour debug
    }
    ```

    - `success`: booléen obligatoire. `false` signifie que le workflow n'a pas produit de résultat exploitable.
    - `source`: permet au pipeline d'identifier l'origine des données.
    - `payload.title` / `payload.author`: champs prioritaires utilisés pour décider du titre/auteur final. Si `success=true`, ces champs devraient être présents.
    - `errors`: utile pour tracer les problèmes. Si `success=false`, la CLI les logge.
    - `raw`: facultatif, mais pratique pour garder la réponse originale (non stockée si elle contient des données sensibles).

    Toute évolution de ce format doit être synchronisée entre les workflows et le client Python.
-   **Stratégie d'appel** :
    1. Si un ISBN normalisé est extrait, le workflow `n8n_isbn` est appelé en premier avec : l'ISBN principal, la liste complète des ISBN candidats, les métadonnées brutes et le nom de fichier.
    2. Si `n8n_isbn` renvoie `success: true`, les données retournées sont utilisées pour finaliser le traitement (aucun autre workflow n'est appelé).
    3. Si aucun ISBN n'est trouvé ou si `n8n_isbn` échoue (`success: false`), le workflow `n8n_metadata` est appelé avec les métadonnées brutes et le nom du fichier.
    4. L'intégration Flowise (check / cover) pourra être branchée suivant les mêmes règles de format lorsque nécessaire.
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
