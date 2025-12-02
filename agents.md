# Notes pour agents / mainteneurs

- **Commandes lentes** : la bibliothèque source contient ~70k EPUB. Lors de tests manuels avec `src/main.py`, toujours limiter la charge (`--limit 1 --dry-run`) sauf instruction contraire. Exemple :
  ```bash
  python3 src/main.py run --limit 1 --dry-run
  ```
- **Workflows externes** :
  - n8n expose deux webhooks (`isbn-lookup`, `metadata-lookup`). Les réponses **doivent** suivre le schéma documenté dans `doc/architecture.md` (`success`, `source`, `payload`, etc.). Toute réponse hors format est considérée comme une erreur.
  - L'appel ISBN reçoit désormais : l'ISBN principal (normalisé sans tirets), la liste complète des ISBN candidats, les métadonnées brutes du fichier et le nom du fichier. Le workflow doit renvoyer `success: true` pour interrompre la chaîne (metadata n'est appelée qu'en cas d'échec ou d'absence d'ISBN).
  - Flowise adoptera la même structure de réponse ; branchements à venir.
- **SSL / Traefik** : en local derrière Traefik avec certificats auto-signés, désactivez la vérification TLS via `services.n8n.verify_ssl: false` (ou `N8N_VERIFY_SSL=false`) pour éviter les erreurs `CERTIFICATE_VERIFY_FAILED`.
- **Logs** : sont stockés dans `logs/processing.log`. Un `--reset` hors dry-run supprime automatiquement le contenu de ce dossier pour repartir proprement.
- **Nettoyage** : les dossiers `__pycache__` sont ignorés mais peuvent être supprimés avec `find src -name '__pycache__' -exec rm -rf {} +` avant un commit si besoin.
