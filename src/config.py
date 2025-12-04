"""
Chargement et validation de la configuration de l'application.

Ce module utilise Pydantic pour lire les variables d'environnement
à partir d'un fichier .env et les valider.
"""
import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List

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

class DatabaseConfig(BaseModel):
    dsn: PostgresDsn

class RedisConfig(BaseModel):
    host: str
    port: int
    db: int

class N8NServiceConfig(BaseModel):
    prod_url: HttpUrl
    test_url: HttpUrl
    workflow_path: str
    verify_ssl: bool = True

class OCRConfig(BaseModel):
    languages: List[str] = ["fr", "en"]
    use_gpu: bool = False
    max_chars: int = 2000
    detail: int = 0
    paragraph: bool = True
    contrast_ths: float = 0.1
    adjust_contrast: float = 0.5
    text_threshold: float = 0.5
    low_text: float = 0.4
    link_threshold: float = 0.4

class ServicesConfig(BaseModel):
    n8n: N8NServiceConfig

class RunCommandConfig(BaseModel):
    dry_run: bool = False
    test_file: Optional[Path] = None
    limit: int = 0
    offset: int = 0
    use_redis: bool = False
    verbose: bool = False
    reset: bool = False
    n8n_test: bool = False

class CommandsConfig(BaseModel):
    run: RunCommandConfig = RunCommandConfig()

class Settings(BaseModel):
    app: AppConfig
    paths: PathsConfig
    database: DatabaseConfig
    redis: RedisConfig
    services: ServicesConfig
    ocr: OCRConfig
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
            config_data.setdefault("paths", {})["book_sources"] = os.getenv("EPUB_DIR")
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
            config_data.setdefault("services", {}).setdefault("n8n", {})["prod_url"] = os.getenv("N8N_BASE_URL")
        if os.getenv("N8N_PROD_URL"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["prod_url"] = os.getenv("N8N_PROD_URL")
        if os.getenv("N8N_TEST_URL"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["test_url"] = os.getenv("N8N_TEST_URL")
        if os.getenv("N8N_VERIFY_SSL"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["verify_ssl"] = os.getenv("N8N_VERIFY_SSL").lower() in ("1", "true", "yes")

        if os.getenv("N8N_WORKFLOW_PATH"):
            config_data.setdefault("services", {}).setdefault("n8n", {})["workflow_path"] = os.getenv("N8N_WORKFLOW_PATH")

        config_data.setdefault("ocr", {})
        if os.getenv("OCR_LANGUAGES"):
            langs = [lang.strip() for lang in os.getenv("OCR_LANGUAGES").split(",") if lang.strip()]
            if langs:
                config_data.setdefault("ocr", {})["languages"] = langs
        if os.getenv("OCR_USE_GPU"):
            config_data.setdefault("ocr", {})["use_gpu"] = os.getenv("OCR_USE_GPU").lower() in ("1", "true", "yes")
        if os.getenv("OCR_MAX_CHARS"):
            config_data.setdefault("ocr", {})["max_chars"] = int(os.getenv("OCR_MAX_CHARS"))
        if os.getenv("OCR_DETAIL"):
            config_data.setdefault("ocr", {})["detail"] = int(os.getenv("OCR_DETAIL"))
        if os.getenv("OCR_PARAGRAPH"):
            config_data.setdefault("ocr", {})["paragraph"] = os.getenv("OCR_PARAGRAPH").lower() in ("1", "true", "yes")
        if os.getenv("OCR_CONTRAST_THS"):
            config_data.setdefault("ocr", {})["contrast_ths"] = float(os.getenv("OCR_CONTRAST_THS"))
        if os.getenv("OCR_ADJUST_CONTRAST"):
            config_data.setdefault("ocr", {})["adjust_contrast"] = float(os.getenv("OCR_ADJUST_CONTRAST"))
        if os.getenv("OCR_TEXT_THRESHOLD"):
            config_data.setdefault("ocr", {})["text_threshold"] = float(os.getenv("OCR_TEXT_THRESHOLD"))
        if os.getenv("OCR_LOW_TEXT"):
            config_data.setdefault("ocr", {})["low_text"] = float(os.getenv("OCR_LOW_TEXT"))
        if os.getenv("OCR_LINK_THRESHOLD"):
            config_data.setdefault("ocr", {})["link_threshold"] = float(os.getenv("OCR_LINK_THRESHOLD"))

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
        return Path(self.paths.book_sources).expanduser()

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
        return str(self.services.n8n.prod_url)

    @property
    def n8n_verify_ssl(self) -> bool:
        return self.services.n8n.verify_ssl

    @property
    def n8n_workflow_path(self) -> str:
        return self.services.n8n.workflow_path

    @property
    def n8n_test_base_url(self) -> str:
        return str(self.services.n8n.test_url)

    @property
    def n8n_test_workflow_path(self) -> str:
        return self.services.n8n.workflow_path

    def _combine_n8n_url(self, base: str, path: str) -> str:
        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    @property
    def n8n_workflow_url(self) -> str:
        return self._combine_n8n_url(self.n8n_base_url, self.n8n_workflow_path)

    @property
    def n8n_test_workflow_url(self) -> str:
        return self._combine_n8n_url(self.n8n_test_base_url, self.n8n_test_workflow_path)

    @property
    def ocr_languages(self) -> List[str]:
        return list(self.ocr.languages)

    @property
    def ocr_use_gpu(self) -> bool:
        return self.ocr.use_gpu

    @property
    def ocr_max_chars(self) -> int:
        return self.ocr.max_chars

    @property
    def ocr_detail(self) -> int:
        return self.ocr.detail

    @property
    def ocr_paragraph(self) -> bool:
        return self.ocr.paragraph

    @property
    def ocr_contrast_ths(self) -> float:
        return self.ocr.contrast_ths

    @property
    def ocr_adjust_contrast(self) -> float:
        return self.ocr.adjust_contrast

    @property
    def ocr_text_threshold(self) -> float:
        return self.ocr.text_threshold

    @property
    def ocr_low_text(self) -> float:
        return self.ocr.low_text

    @property
    def ocr_link_threshold(self) -> float:
        return self.ocr.link_threshold

# Instance globale des réglages
try:
    settings = Settings.load()
except Exception as e:
    print(f"Erreur de configuration : {e}")
    print("Veuillez vérifier votre fichier .env et config/config.yaml.")
    exit(1)
