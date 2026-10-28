from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./robotic_mind.db"
    llm_mode: Literal["mock", "nebius"] = "mock"
    strict_hackathon_mode: bool = False
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_model: str = "nvidia/nemotron-3-super-120b-a12b"
    dedup_radius: float = 0.8
    stale_seconds: float = 10
    offline_seconds: float = 25

    @model_validator(mode="after")
    def provider_valid(self):
        if self.strict_hackathon_mode and self.llm_mode != "nebius":
            raise ValueError("STRICT_HACKATHON_MODE requires LLM_MODE=nebius")
        if self.llm_mode == "nebius" and not self.nebius_api_key:
            raise ValueError("NEBIUS_API_KEY is required for Nebius mode")
        return self
