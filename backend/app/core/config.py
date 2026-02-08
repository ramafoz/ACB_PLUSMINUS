from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- DB ---
    DATABASE_URL: str = "sqlite:///./acb_game.sqlite"

    # --- JWT ---
    JWT_SECRET: str = "Na_portada_da_Gigantes_Enero_2026_sae_Hugo_Celtics"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MIN: int = 10080  # 7 días

    # Le dice a Pydantic que lea del archivo .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instancia global para importar en el resto del proyecto
settings = Settings()
