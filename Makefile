.PHONY: clean-dev
clean-dev:
	@echo -n "Are you sure? [yes/N] (this will delete volumes) " && read ans && [ $${ans:-N} = yes ]
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes --remove-orphans

.PHONY: dev
dev:
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml build
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --remove-orphans

.PHONY: dev-redis-only
dev-redis-only:
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml build redis
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --remove-orphans redis

.PHONY: stop-dev
stop-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes

.PHONY: prod
prod:
	docker compose --env-file .env.prod build
	docker compose --env-file .env.prod up -d --remove-orphans
	docker buildx prune --keep-storage 20gb -f
	docker image prune -f
	docker system df

.PHONY: stop-prod
stop-prod:
	docker compose down
