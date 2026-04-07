"""Configuration loading and validation using pydantic v2."""

import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "gemini", "ollama"]
    api_key: str | None = None
    model: str | None = None
    ollama_url: str = "http://localhost:11434"


class FamilyConfig(BaseModel):
    name: str
    target_language: str = "en"
    dialect: str | None = None
    preserve_terms: list[str] = []
    trigger_mode: Literal["auto", "reaction", "command"] = "auto"
    reaction_trigger: str = "\U0001f310"
    command_prefix: str = "!translate"
    rooms: list[str] = ["*"]


class MatrixConfig(BaseModel):
    homeserver_url: str
    access_token: str
    user_id: str


class Config(BaseModel):
    family: FamilyConfig
    matrix: MatrixConfig
    llm: LLMConfig


def load_config(path: str | Path) -> Config:
    """Load and validate config from a YAML file. Exits on error."""
    path = Path(path)
    if not path.exists():
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        print(f"ERROR: Config file is empty: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        return Config(**raw)
    except ValidationError as e:
        print(f"ERROR: Invalid configuration:\n{e}", file=sys.stderr)
        sys.exit(1)
