"""
Chargement et validation de la configuration de l'application.

Ce module utilise Pydantic pour lire les variables d'environnement
à partir d'un fichier .env et les valider.
"""
import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, PostgresDsn

# Charger le fichier .env se trouvant à la racine du projet
dotenv_path = Path(__file__).parent.parent / ".env" # Point to project root
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)


class AppConfig(BaseModel):
    name: str
    text_preview_chars: int
    request_timeout: int

class PathsConfig(BaseModel):
    book_sources: Path
    book_target: Path
    epub_directory: Path

class DatabaseConfig(BaseModel):
    dsn: PostgresDsn

class RedisConfig(BaseModel):
    host: str
    port: int
    db: int

class N8NServiceConfig(BaseModel):
    base_url: HttpUrl
    isbn_path: str
    metadata_path: str

class FlowiseServiceConfig(BaseModel):
    base_url: HttpUrl
    check_flow_id: str
    cover_flow_id: str

class ServicesConfig(BaseModel):
    n8n: N8NServiceConfig
    flowise: FlowiseServiceConfig

class RunCommandConfig(BaseModel):
    dry_run: bool = False
    test_file: Optional[Path] = None
    limit: int = 0
    offset: int = 0
    use_redis: bool = False
    verbose: bool = False
    reset: bool = False

class CommandsConfig(BaseModel):
    run: RunCommandConfig = RunCommandConfig()

class Settings(BaseModel):
    app: AppConfig
    paths: PathsConfig
    database: DatabaseConfig
    redis: RedisConfig
    services: ServicesConfig
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def load(cls, config_file: Path = Path(__file__).parent.parent / "config" / "config.yaml") -> "Settings":
        """
        Loads configuration from config.yaml and overrides with environment variables.
        Environment variables take precedence.
        """
        config_data: Dict[str, Any] = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f)
        
        # Apply environment variable overrides
        # This part assumes env vars are named to directly map to the fields.
        # For nested structures, we apply them manually.
        
        # Database DSN
        if os.getenv("POSTGRES_DSN"):
            config_data.setdefault("database", {})["dsn"] = os.getenv("POSTGRES_DSN")
        
        # Redis
        if os.getenv("REDIS_HOST"):
            config_data.setdefault("redis", {})["host"] = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            config_data.setdefault("redis", {})["port"] = int(os.getenv("REDIS_PORT"))
        if os.getenv("REDIS_DB"):
            config_data.setdefault("redis", {})["db"] = int(os.getenv("REDIS_DB"))

        # Paths
        if os.getenv("EPUB_DIR"):
            config_data.setdefault("paths", {})["epub_directory"] = os.getenv("EPUB_DIR")
        if os.getenv("BOOK_SOURCES"):
            config_data.setdefault("paths", {})["book_sources"] = os.getenv("BOOK_SOURCES")
        if os.getenv("BOOK_TARGET"):
            config_data.setdefault("paths", {})["book_target"] = os.getenv("BOOK_TARGET")

        # App settings
        if os.getenv("APP_NAME"):
            config_data.setdefault("app", {})["name"] = os.getenv("APP_NAME")
        if os.getenv("TEXT_PREVIEW_CHARS"):
            config_data.setdefault("app", {})["text_preview_chars"] = int(os.getenv("TEXT_PREVIEW_CHARS"))
        if os.getenv("REQUEST_TIMEOUT"):
            config_data.setdefault("app", {})["request_timeout"] = int(os.getenv("REQUEST_TIMEOUT"))

        # N8N Services
        if os.getenv("N8N_BASE_URL"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["base_url"] = os.getenv("N8N_BASE_URL")
        if os.getenv("N8N_ISBN_PATH"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["isbn_path"] = os.getenv("N8N_ISBN_PATH")
        if os.getenv("N8N_METADATA_PATH"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["metadata_path"] = os.getenv("N8N_METADATA_PATH")

        # Flowise Services
        if os.getenv("FLOWISE_BASE_URL"):
            config_data.setdefault("services", {}).setdefault("flowise", {})["base_url"] = os.getenv("FLOWISE_BASE_URL")
        if os.getenv("FLOWISE_CHECK_ID"):
            config_data.setdefault("services", {}).setdefault("flowise", {})["check_flow_id"] = os.getenv("FLOWISE_CHECK_ID")
        if os.getenv("FLOWISE_COVER_ID"):
            config_data.setdefault("services", {}).setdefault("flowise", {})["cover_flow_id"] = os.getenv("FLOWISE_COVER_ID")


        return cls(**config_data)

    # Convenience accessors used throughout the codebase
    @property
    def app_name(self) -> str:
        return self.app.name

    @property
    def text_preview_chars(self) -> int:
        return self.app.text_preview_chars

    @property
    def request_timeout(self) -> int:
        return self.app.request_timeout

    @property
    def epub_dir(self) -> Path:
        return Path(self.paths.epub_directory).expanduser()

    @property
    def postgres_dsn(self) -> PostgresDsn:
        return self.database.dsn

    @property
    def redis_host(self) -> str:
        return self.redis.host

    @property
    def redis_port(self) -> int:
        return self.redis.port

    @property
    def redis_db(self) -> int:
        return self.redis.db

    @property
    def n8n_base_url(self) -> str:
        return str(self.services.n8n.base_url)

    @property
    def n8n_isbn_path(self) -> str:
        return self.services.n8n.isbn_path

    @property
    def n8n_metadata_path(self) -> str:
        return self.services.n8n.metadata_path

    @property
    def n8n_test_base_url(self) -> str:
        return self.n8n_base_url

    @property
    def n8n_test_isbn_path(self) -> str:
        return self.n8n_isbn_path

    @property
    def n8n_test_metadata_path(self) -> str:
        return self.n8n_metadata_path

    @property
    def flowise_base_url(self) -> str:
        return str(self.services.flowise.base_url)

    @property
    def flowise_check_id(self) -> str:
        return self.services.flowise.check_flow_id

    @property
    def flowise_cover_id(self) -> str:
        return self.services.flowise.cover_flow_id

    @property
    def flowise_test_base_url(self) -> str:
        return self.flowise_base_url

    @property
    def flowise_test_check_id(self) -> str:
        return self.flowise_check_id

    @property
    def flowise_test_cover_id(self) -> str:
        return self.flowise_cover_id

# Instance globale des réglages
try:
    settings = Settings.load()
except Exception as e:
    print(f"Erreur de configuration : {e}")
    print("Veuillez vérifier votre fichier .env et config/config.yaml.")
    exit(1)
