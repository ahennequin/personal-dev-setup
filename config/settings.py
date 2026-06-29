from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # GitHub (user identity — used as fallback when bot identity is not configured)
    github_pat: str
    github_webhook_secret: str
    github_username: str
    github_repos: list[str] = []

    # GitHub App (bot identity — optional; when set, all spec-kit API calls
    # use the bot's installation token instead of the user's PAT)
    github_app_id: str = ""
    github_app_private_key_path: Path = Path("")

    @field_validator("github_app_private_key_path", mode="before")
    @classmethod
    def expand_path(cls, v):
        if isinstance(v, str) and v.startswith("~"):
            return Path(v).expanduser()
        return v
    github_app_installation_id: str = ""
    github_bot_username: str = ""

    @property
    def has_bot_identity(self) -> bool:
        return bool(
            self.github_app_id
            and self.github_app_private_key_path
            and self.github_app_installation_id
            and self.github_bot_username
        )

    @field_validator("github_repos", mode="before")
    @classmethod
    def split_github_repos(cls, v):
        if isinstance(v, str):
            return [r.strip() for r in v.split(",") if r.strip()]
        return v or []

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
