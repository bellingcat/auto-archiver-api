clean-dev:
	@echo -n "Are you sure? [yes/N] (this will delete volumes) " && read ans && [ $${ans:-N} = yes ]
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes --remove-orphans

dev:
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml build
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --remove-orphans


dev-redis-only:
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml build redis
	docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --remove-orphans redis

stop-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes

prod:
	docker compose --env-file .env.prod build
	docker compose --env-file .env.prod up -d --remove-orphans
	docker buildx prune --keep-storage 20gb -f
	docker image prune -f
	docker system df

stop-prod:
	docker compose down