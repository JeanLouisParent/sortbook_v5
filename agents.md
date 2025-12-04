# Notes pour agents / mainteneurs

- **Commandes lentes** : la bibliothèque source contient ~70k EPUB. Lors de tests manuels avec `src/main.py`, toujours limiter la charge (`--limit 1 --dry-run`) sauf instruction contraire. Exemple :
  ```bash
  python3 src/main.py run --limit 1 --dry-run
  ```
- **Workflows externes** :
  - n8n expose un seul webhook (`sortebook_v5`) qui reçoit tout le payload (`file`, `metadata`, `isbn`, `text_preview`, `cover`, `dry_run`, `test_mode`). Le format complet est documenté dans `doc/architecture.md`.
  - Le workflow doit renvoyer un JSON standardisé (`success`, `source`, `payload.title`, `payload.author`). Toute réponse hors format est considérée comme une erreur et marque le livre `failed`.
  - Flowise reste disponible, mais c’est n8n qui gère désormais les appels vers ce type de service.
- **SSL / Traefik** : en local derrière Traefik avec certificats auto-signés, désactivez la vérification TLS via `services.n8n.verify_ssl: false` (ou `N8N_VERIFY_SSL=false`) pour éviter les erreurs `CERTIFICATE_VERIFY_FAILED`.
- **Logs** : sont stockés dans `logs/processing.log`. Un `--reset` hors dry-run supprime automatiquement le contenu de ce dossier pour repartir proprement.
- **Nettoyage** : les dossiers `__pycache__` sont ignorés mais peuvent être supprimés avec `find src -name '__pycache__' -exec rm -rf {} +` avant un commit si besoin.
