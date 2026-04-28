from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_compose_has_opt_in_whatsapp_service_profile() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    whatsapp = compose["services"]["whatsapp"]
    assert whatsapp["image"] == "dock.mau.fi/mautrix/whatsapp:latest"
    assert "whatsapp" in whatsapp["profiles"]
    assert "./whatsapp-data:/data" in whatsapp["volumes"]


def test_makefile_has_whatsapp_targets() -> None:
    makefile = (ROOT / "Makefile").read_text()
    assert "docker-whatsapp-up:" in makefile
    assert "docker-whatsapp-down:" in makefile
    assert "docker-whatsapp-logs:" in makefile
    assert "$(COMPOSE) --profile whatsapp up -d whatsapp" in makefile


def test_whatsapp_templates_exist_and_parse() -> None:
    wa_template = ROOT / "whatsapp-data" / "config.example.yaml"
    lb_template = ROOT / "config" / "config-local-whatsapp.example.yaml"
    assert wa_template.exists()
    assert lb_template.exists()

    wa_cfg = yaml.safe_load(wa_template.read_text())
    lb_cfg = yaml.safe_load(lb_template.read_text())

    assert wa_cfg["appservice"]["id"] == "whatsapp"
    assert wa_cfg["bridge"]["command_prefix"] == "!wa"
    assert lb_cfg["family"]["rooms"]
    assert lb_cfg["matrix"]["encryption"]["enabled"] is True
