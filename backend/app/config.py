from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    participants: list[Literal["human", "ai"]] = Field(min_length=3, max_length=3)
    discussion_seconds: int = Field(default=60, ge=1, le=300)
    voting_seconds: int = Field(default=30, ge=1, le=120)
    feedback_seconds: int = Field(default=6, ge=1, le=30)
    waiting_seconds: int = Field(default=180, ge=10, le=600)
    rounds: Literal[2] = 2

    @model_validator(mode="after")
    def needs_a_human(self):
        if "human" not in self.participants:
            raise ValueError("At least one human participant is required")
        return self


def load_settings(path: str) -> Settings:
    return Settings.model_validate(yaml.safe_load(Path(path).read_text()))
