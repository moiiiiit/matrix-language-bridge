"""Configuration loading and validation using pydantic v2."""

import logging
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "gemini", "ollama"]
    api_key: str | None = None
    model: str | None = None
    ollama_url: str = "http://localhost:11434"


class FamilyConfig(BaseModel):
    name: str
    profile: str = "default"
    room_profiles: dict[str, str] = Field(default_factory=dict)
    # Legacy fields kept for backward compatibility with old configs.
    dialect: str | None = None
    preserve_terms: list[str] = []
    trigger_mode: Literal["auto", "reaction", "command"] = "auto"
    reaction_trigger: str = "\U0001f310"
    command_prefix: str = "!translate"
    rooms: list[str] = ["*"]


class MatrixEncryptionConfig(BaseModel):
    """Megolm/Olm encryption. Install with ``poetry install --extras e2ee`` plus system libolm."""

    enabled: bool = False
    store_path: str = "data/languagebridge-e2ee.db"
    pickle_key: str = ""


class MatrixConfig(BaseModel):
    homeserver_url: str
    access_token: str = ""
    password: str | None = None
    user_id: str
    encryption: MatrixEncryptionConfig = Field(default_factory=MatrixEncryptionConfig)


class UIConfig(BaseModel):
    """How bot messages are rendered in Matrix clients (Element, Beeper, etc.).

    Matrix allows a small HTML subset — not full CSS. ``subtle`` uses muted
    color and optional ``<small>`` so translations and notices look secondary.
    """

    message_style: Literal["normal", "subtle"] = "subtle"
    subtle_text_color: str = "#8E9597"
    subtle_use_small: bool = True


class TranslationProfile(BaseModel):
    id: str
    target_language: str
    reply_target_label: str
    bidirectional_with: str | None = None
    prompt_appendix: str = ""
    dialect: str | None = None
    preserve_terms: list[str] = Field(default_factory=list)


class Config(BaseModel):
    family: FamilyConfig
    matrix: MatrixConfig
    llm: LLMConfig
    ui: UIConfig = Field(default_factory=UIConfig)
    profiles: dict[str, TranslationProfile]

    def profile_for_room(self, room_id: str) -> TranslationProfile:
        profile_name = self.family.room_profiles.get(room_id, self.family.profile)
        return self.profiles[profile_name]

    @property
    def default_profile(self) -> TranslationProfile:
        return self.profiles[self.family.profile]


def _resolve_profile_path(profile_name: str, config_path: Path) -> Path:
    candidate = Path(profile_name)
    if candidate.exists():
        return candidate

    config_relative = config_path.parent / profile_name
    if config_relative.exists():
        return config_relative

    package_profiles = Path(__file__).with_name("profiles")
    normalized = profile_name if profile_name.endswith(".yaml") else f"{profile_name}.yaml"
    package_candidate = package_profiles / normalized
    if package_candidate.exists():
        return package_candidate

    print(
        f"ERROR: Profile not found: {profile_name}. "
        f"Tried {candidate}, {config_relative}, and {package_candidate}",
        file=sys.stderr,
    )
    sys.exit(1)


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

    family_raw = raw.get("family", {})
    default_profile_name = family_raw.get("profile", "default")
    room_profiles = family_raw.get("room_profiles", {}) or {}
    names_to_load = {default_profile_name, *room_profiles.values()}
    logger.debug(
        "Resolving profiles: default=%s room_profiles=%s",
        default_profile_name,
        room_profiles,
    )

    loaded_profiles: dict[str, dict] = {}
    for profile_name in names_to_load:
        profile_path = _resolve_profile_path(profile_name, path)
        with open(profile_path) as f:
            raw_profile = yaml.safe_load(f)
        if not raw_profile:
            print(f"ERROR: Profile file is empty: {profile_path}", file=sys.stderr)
            sys.exit(1)
        loaded_profiles[profile_name] = raw_profile
        logger.debug("Loaded profile '%s' from %s", profile_name, profile_path)

    # Back-compat: if legacy fields exist under family, apply them to profiles
    # only when the profile doesn't define its own values.
    family_dialect = family_raw.get("dialect")
    family_terms = family_raw.get("preserve_terms")
    for profile_data in loaded_profiles.values():
        if family_dialect and not profile_data.get("dialect"):
            profile_data["dialect"] = family_dialect
        if family_terms and not profile_data.get("preserve_terms"):
            profile_data["preserve_terms"] = family_terms

    raw["profiles"] = loaded_profiles

    try:
        cfg = Config(**raw)
        logger.debug("Config validation complete.")
        return cfg
    except ValidationError as e:
        print(f"ERROR: Invalid configuration:\n{e}", file=sys.stderr)
        sys.exit(1)
