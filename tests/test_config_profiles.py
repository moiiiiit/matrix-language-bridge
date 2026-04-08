from pathlib import Path

from languagebridge.config import load_config


def _write_config(path: Path, profile: str = "default") -> None:
    path.write_text(
        "\n".join(
            [
                "family:",
                "  name: Test Family",
                f"  profile: {profile}",
                "matrix:",
                "  homeserver_url: https://matrix.org",
                "  access_token: token",
                "  user_id: '@bot:matrix.org'",
                "llm:",
                "  provider: anthropic",
                "  api_key: key",
            ]
        )
    )


def test_loads_builtin_default_profile(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, profile="default")

    cfg = load_config(cfg_path)

    assert cfg.family.profile == "default"
    assert cfg.default_profile.id == "default"
    assert cfg.default_profile.target_language == "en"
    assert cfg.default_profile.reply_target_label == "en"


def test_loads_builtin_charje_profile(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, profile="charje_english_runes")

    cfg = load_config(cfg_path)

    assert cfg.default_profile.id == "charje_english_runes"
    assert cfg.default_profile.reply_target_label == "en"
    assert cfg.default_profile.target_language == "en"
    assert "Charje" in cfg.default_profile.prompt_appendix
    assert "charje.net" in cfg.default_profile.prompt_appendix


def test_loads_profile_from_absolute_path(tmp_path: Path) -> None:
    custom_profile = tmp_path / "my_profile.yaml"
    custom_profile.write_text(
        "\n".join(
            [
                "id: custom",
                "target_language: fr",
                "reply_target_label: fr-custom",
                "prompt_appendix: use custom style",
            ]
        )
    )

    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, profile=str(custom_profile))

    cfg = load_config(cfg_path)

    assert cfg.default_profile.id == "custom"
    assert cfg.default_profile.target_language == "fr"
    assert cfg.default_profile.reply_target_label == "fr-custom"


def test_loads_per_room_profile_mapping(tmp_path: Path) -> None:
    custom_profile = tmp_path / "my_profile.yaml"
    custom_profile.write_text(
        "\n".join(
            [
                "id: custom",
                "target_language: fr",
                "reply_target_label: fr-custom",
                "prompt_appendix: use custom style",
            ]
        )
    )
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "family:",
                "  name: Test Family",
                "  profile: default",
                "  room_profiles:",
                f"    '!room:matrix.org': {custom_profile}",
                "matrix:",
                "  homeserver_url: https://matrix.org",
                "  access_token: token",
                "  user_id: '@bot:matrix.org'",
                "llm:",
                "  provider: anthropic",
                "  api_key: key",
            ]
        )
    )

    cfg = load_config(cfg_path)
    per_room = cfg.profile_for_room("!room:matrix.org")
    fallback = cfg.profile_for_room("!other:matrix.org")

    assert per_room.id == "custom"
    assert per_room.target_language == "fr"
    assert fallback.id == "default"
