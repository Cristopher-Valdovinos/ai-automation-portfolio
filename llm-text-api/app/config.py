"""Configuración de la API, leída desde variables de entorno o un archivo .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 127.0.0.1 en vez de "localhost": en Windows, "localhost" intenta primero
    # IPv6 y agrega unos 2 segundos a cada llamada a Ollama.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: float = 120.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
