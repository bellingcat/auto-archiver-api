clean-dev:
	@echo -n "Are you sure? [yes/N] (this will delete volumes) " && read ans && [ $${ans:-N} = yes ]
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes --remove-orphans

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --remove-orphans

stop-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes

prod:
	docker compose build
	docker compose up -d --remove-orphans

stop-prod:
	docker compose down