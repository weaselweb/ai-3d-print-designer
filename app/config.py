"""Application settings, loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    anthropic_max_tokens: int = 8000

    # Image/text-to-3D (organic/figurine shapes CadQuery can't sculpt)
    meshy_api_key: str = ""

    # App
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    data_dir: Path = Path("./data")

    # Printer profile — drives the print-readiness checks and the AI prompt.
    nozzle_diameter: float = 0.4          # mm
    layer_height: float = 0.2             # mm
    overhang_threshold_deg: float = 45.0  # steeper (more horizontal) overhangs need support
    default_clearance: float = 0.2        # mm per side, for mating parts

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    def ensure_dirs(self) -> None:
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
