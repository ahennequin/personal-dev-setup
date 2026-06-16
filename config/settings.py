from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # GitHub
    github_pat: str
    github_webhook_secret: str
    github_username: str

    # OpenCode
    opencode_model: str = "opencode/deepseek-v4-flash-free"

    # Paths
    repos_base_path: Path = Path.home() / "Code"
    speckit_data_path: Path = Path.home() / ".local" / "share" / "speckit"

    # API
    api_port: int = 8080

    @property
    def state_db_path(self) -> str:
        return str(self.speckit_data_path / "state.db")

    @property
    def traces_db_path(self) -> str:
        return str(self.speckit_data_path / "traces.db")

    def repo_path(self, repo_name: str) -> Path:
        return self.repos_base_path / repo_name

    def ensure_data_dir(self) -> None:
        self.speckit_data_path.mkdir(parents=True, exist_ok=True)


# Singleton — import this everywhere
settings = Settings()
