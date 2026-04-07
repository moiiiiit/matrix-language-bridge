APP_NAME := languagebridge
COMPOSE := docker compose

.PHONY: setup install run shell lock docker-build docker-up docker-down docker-restart docker-logs docker-ps

setup:
	@if [ -f config/config.yaml ]; then \
		echo "config/config.yaml already exists"; \
	else \
		cp config/config.example.yaml config/config.yaml; \
		echo "Created config/config.yaml from template"; \
	fi

install:
	poetry install

run:
	poetry run languagebridge

shell:
	poetry shell

lock:
	poetry lock

docker-build:
	$(COMPOSE) build

docker-up:
	$(COMPOSE) up -d

docker-down:
	$(COMPOSE) down

docker-restart:
	$(COMPOSE) restart $(APP_NAME)

docker-logs:
	$(COMPOSE) logs -f $(APP_NAME)

docker-ps:
	$(COMPOSE) ps
