# Architecture du Projet

Ce document synthétise la nouvelle architecture du pipeline `sortbook_v5`, maintenant centrée sur une seule intégration côté n8n.

## Vue d'ensemble

Le traitement d'un EPUB suit trois grandes étapes :

1.  **Extraction locale** (hash, métadonnées, texte, couverture, ISBN...).
2.  **Appel unique à n8n** via le workflow `sortebook_v5` : c’est lui qui orchestre les vérifications complémentaires (Flowise, API externes, règles heuristiques, etc.) et renvoie un titre/auteur final.
3.  **Persistance** des données dans PostgreSQL + suivi Redis, avec un log de bord pour chaque fichier.

Le code Python se concentre exclusivement sur l’extraction et l’interface avec PostgreSQL/Redis ; toute la logique d’enrichissement, de déduplication sensible ou d’appel à Flowise se trouve désormais dans n8n.

## Composants principaux

### 1. Application Python (`src/`)

- `src/main.py`: CLI Click qui :
  - génère la liste des `.epub` (avec offset/limit et option Redis),
  - contrôle les options `--dry-run`, `--reset`, `--n8n-test`,
  - lance `src/core/pipeline.py` pour chaque fichier en mode séquentiel.
- `src/core/pipeline.py`: pipeline allégé qui :
  - calcule le SHA256 et vérifie les doublons `hash`/`ISBN` via PostgreSQL,
  - extrait métadonnées, texte (limité à `text_preview_chars`), couverture et ISBN via `src/tasks/extract.py`,
  - construit le payload JSON (voir plus bas) et appelle le webhook n8n `sortebook_v5`,
  - stocke la réponse (champ `json_n8n_response`) et le titre/auteur final, puis met à jour la base et l’état Redis.

- `src/tasks/extract.py`: toujours responsable des extractions brutes (hash, couverture propre, ISBN, métadonnées non transformées, aperçu textuel).
- `src/tasks/integrate.py`: expose `call_n8n_sortebook_workflow` qui envoie tout le payload JSON à n8n et valide que `success` + `payload.title`/`payload.author` sont présents.
- `src/db/database.py`: gère les inserts/updates dans le schéma `book_data.books`.
- `src/core/reporting.py`: centralise la mise en forme des lignes de console.

**Payload envoyé à n8n (`sortebook_v5`)**

```json
{
  "filename": "mon-livre.epub",
  "metadata": { ... },         // structure brute retournée par ebooklib
  "isbn": {
    "metadata": ["978..."],
    "text": [],
    "ocr": ["978..."]
  },
  "text_preview": "Extrait du texte...",
  "ocr": [
    {
      "filename": "cover.jpg",
      "text": "ISBN 978..."
    }
  ]
}
```

Le workflow `sortebook_v5` peut appeler n’importe quel autre service (Flowise, API bibliographiques, etc.) et doit renvoyer un objet JSON standardisé :

```json
{
  "success": true,
  "source": "sortebook_v5",
  "payload": {
    "title": "Titre final",
    "author": "Auteur final"
  },
  "errors": [],
  "raw": { ... }
}
```

La réponse est stockée dans PostgreSQL sous `json_n8n_response`; si `success=false`, le pipeline marque le livre `failed` et enregistre les erreurs.

### 2. n8n (service d’automatisation)

- `n8n` expose un seul webhook (`sortebook_v5`) qui reçoit l’intégralité des données extraites.
- C’est ce workflow qui peut contacter Flowise, mettre en œuvre des règles métier et valider les doublons intelligemment.
- Il renvoie toujours les champs requis (`success`, `source`, `payload.{title,author}`) pour que l’application Python puisse clore le traitement.

### 3. PostgreSQL

- Schéma principal `book_data.books` (voir `database/schema.sql`). Il conserve : hash, chemin, métadonnées brutes (`json_extract_*`), réponse n8n (`json_n8n_response`), statut (`pending`, `processed`, `duplicate_hash`, `duplicate_isbn`, `failed`) et décision finale (`final_title`, `final_author`, `choice_source`).
- Le pipeline écrit l’entrée `pending` puis la met à jour après traitement.
- L’option `--reset` tronque complètement ce schéma via `scripts/init_db.py`.

### 4. Redis

- Stocke la liste `book_processor:processed_files` pour ignorer les EPUB déjà traités quand `--use-redis` est activé.
- `src/core/state.py` gère la connexion, l’ajout et la réinitialisation de cet ensemble.

### 5. Traefik

- Route les appels vers l’instance n8n (et Flowise si tu en as besoin) dans ton environnement Docker local.
- Tes règles Traefik doivent exposer `n8n.mondomaine.local` ou l’équivalent que tu renseignes dans `config/config.yaml`.
