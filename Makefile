# Common dev tasks. Run on the Docker host (or any machine with Docker + compose).
# `make help` lists targets. On Windows use Git Bash, WSL, or run the docker commands
# directly (see each target).

.DEFAULT_GOAL := help
ENV_FILE := .env

.PHONY: help env up down restart ps logs psql redis-cli minio-console rabbitmq-ui hooks

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f $(ENV_FILE) || (cp .env.example $(ENV_FILE) && echo "Created $(ENV_FILE) — edit secrets before `make up`.")

up: env ## Start the backing-services stack (detached)
	docker compose up -d --build

down: ## Stop the stack (keeps volumes/data)
	docker compose down

restart: down up ## Restart the stack

ps: ## Show service status/health
	docker compose ps

logs: ## Tail logs (CTRL-C to stop)
	docker compose logs -f

psql: ## Open psql in the postgres container
	docker compose exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

redis-cli: ## Open redis-cli
	docker compose exec redis redis-cli

minio-console: ## Print the MinIO web console URL
	@echo "MinIO console: http://localhost:$${MINIO_CONSOLE_PORT:-9001}"

rabbitmq-ui: ## Print the RabbitMQ management URL
	@echo "RabbitMQ UI: http://localhost:$${RABBITMQ_MGMT_PORT:-15672}"

hooks: ## Install pre-commit hooks
	pre-commit install
