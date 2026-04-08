"""Generate config/config.yaml from explicit parameters."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_room_profiles(value: str | None) -> dict[str, str]:
    """Parse room profile mappings from 'room=profile,room2=profile2'."""
    if not value:
        return {}
    pairs: dict[str, str] = {}
    for item in value.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        room, profile = item.split("=", 1)
        room = room.strip()
        profile = profile.strip()
        if room and profile:
            pairs[room] = profile
    return pairs


def _require(name: str, value: str | None) -> str:
    if value:
        return value
    print(f"ERROR: Missing required value for {name}", file=sys.stderr)
    sys.exit(1)


def _arg_or_env(args: argparse.Namespace, field: str, env_name: str) -> str | None:
    value = getattr(args, field)
    return value if value is not None else os.environ.get(env_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate LanguageBridge YAML config from flags/env vars."
    )
    parser.add_argument("--output", default="config/config.yaml")

    # family
    parser.add_argument("--family-name")
    parser.add_argument("--profile")
    parser.add_argument("--dialect")
    parser.add_argument("--preserve-terms")
    parser.add_argument("--trigger-mode")
    parser.add_argument("--reaction-trigger")
    parser.add_argument("--command-prefix")
    parser.add_argument("--rooms")
    parser.add_argument(
        "--room-profiles",
        help='CSV mapping: "!roomA:matrix.org=default,!roomB:matrix.org=charje_english_runes"',
    )

    # matrix
    parser.add_argument("--homeserver-url")
    parser.add_argument("--access-token")
    parser.add_argument("--user-id")

    # llm
    parser.add_argument("--provider")
    parser.add_argument("--api-key")
    parser.add_argument("--model")
    parser.add_argument("--ollama-url")

    args = parser.parse_args()

    family_name = _require(
        "family-name / LB_FAMILY_NAME",
        _arg_or_env(args, "family_name", "LB_FAMILY_NAME"),
    )
    profile = _arg_or_env(args, "profile", "LB_PROFILE") or "default"
    dialect = _arg_or_env(args, "dialect", "LB_DIALECT")
    preserve_terms_raw = _arg_or_env(args, "preserve_terms", "LB_PRESERVE_TERMS")
    trigger_mode = _arg_or_env(args, "trigger_mode", "LB_TRIGGER_MODE") or "auto"
    reaction_trigger = (
        _arg_or_env(args, "reaction_trigger", "LB_REACTION_TRIGGER") or "🌐"
    )
    command_prefix = (
        _arg_or_env(args, "command_prefix", "LB_COMMAND_PREFIX") or "!translate"
    )
    rooms_raw = _arg_or_env(args, "rooms", "LB_ROOMS") or "*"
    room_profiles_raw = _arg_or_env(args, "room_profiles", "LB_ROOM_PROFILES")
    homeserver_url = _require(
        "homeserver-url / LB_MATRIX_HOMESERVER_URL",
        _arg_or_env(args, "homeserver_url", "LB_MATRIX_HOMESERVER_URL"),
    )
    access_token = _require(
        "access-token / LB_MATRIX_ACCESS_TOKEN",
        _arg_or_env(args, "access_token", "LB_MATRIX_ACCESS_TOKEN"),
    )
    user_id = _require(
        "user-id / LB_MATRIX_USER_ID",
        _arg_or_env(args, "user_id", "LB_MATRIX_USER_ID"),
    )

    provider = _require(
        "provider / LB_LLM_PROVIDER",
        _arg_or_env(args, "provider", "LB_LLM_PROVIDER"),
    )
    api_key = _arg_or_env(args, "api_key", "LB_LLM_API_KEY")
    model = _arg_or_env(args, "model", "LB_LLM_MODEL")
    ollama_url = _arg_or_env(args, "ollama_url", "LB_LLM_OLLAMA_URL")

    preserve_terms = _split_csv(preserve_terms_raw)
    rooms = _split_csv(rooms_raw) or ["*"]
    room_profiles = _split_room_profiles(room_profiles_raw)

    config: dict[str, object] = {
        "family": {
            "name": family_name,
            "profile": profile,
            "dialect": dialect,
            "preserve_terms": preserve_terms,
            "trigger_mode": trigger_mode,
            "reaction_trigger": reaction_trigger,
            "command_prefix": command_prefix,
            "rooms": rooms,
            "room_profiles": room_profiles,
        },
        "matrix": {
            "homeserver_url": homeserver_url,
            "access_token": access_token,
            "user_id": user_id,
        },
        "llm": {
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "ollama_url": ollama_url or "http://localhost:11434",
        },
    }

    # Keep YAML concise by dropping null optional keys.
    family = config["family"]
    llm = config["llm"]
    if not family["dialect"]:
        family.pop("dialect")
    if not family["room_profiles"]:
        family.pop("room_profiles")
    if not llm["api_key"]:
        llm.pop("api_key")
    if not llm["model"]:
        llm.pop("model")
    if provider != "ollama" and (not ollama_url):
        llm.pop("ollama_url")

    ui_from_env: dict[str, object] = {}
    if us := os.environ.get("LB_UI_MESSAGE_STYLE"):
        ui_from_env["message_style"] = us
    if uc := os.environ.get("LB_UI_SUBTLE_COLOR"):
        ui_from_env["subtle_text_color"] = uc
    if (usm := os.environ.get("LB_UI_SUBTLE_USE_SMALL")) is not None:
        ui_from_env["subtle_use_small"] = usm.lower() in ("1", "true", "yes")
    if ui_from_env:
        config["ui"] = ui_from_env

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    print(f"Wrote config to {output_path}")


if __name__ == "__main__":
    main()
