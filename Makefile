APP_NAME := languagebridge
COMPOSE := docker compose
CONFIG_LOCAL ?= config/config-local.yaml

.PHONY: setup config-from-env test run run-local \
	docker-build docker-up docker-down docker-restart docker-logs docker-ps docker-test \
	docker-run-local

setup:
	@if [ -f config/config.yaml ]; then \
		echo "config/config.yaml already exists"; \
	else \
		cp config/config.example.yaml config/config.yaml; \
		echo "Created config/config.yaml from template"; \
	fi

config-from-env:
	python -m languagebridge.config_gen

test:
	$(MAKE) docker-test

run:
	$(MAKE) docker-up

run-local:
	$(MAKE) docker-run-local

docker-build:
	$(COMPOSE) build

docker-test:
	$(COMPOSE) --profile test run --rm languagebridge-test

# Same idea as run-local: config-local.yaml + DEBUG + ./data (works with matrix.encryption / E2EE in the image).
docker-run-local:
	mkdir -p data
	$(COMPOSE) --profile local run --rm languagebridge-local

docker-up:
	$(COMPOSE) up

docker-down:
	$(COMPOSE) down --remove-orphans

docker-restart:
	$(COMPOSE) restart $(APP_NAME)

docker-logs:
	$(COMPOSE) logs -f $(APP_NAME)

docker-ps:
	$(COMPOSE) ps
