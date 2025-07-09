.PHONY: lint
lint:
	poetry run pre-commit run --all-files

.PHONY: test
test:
	export ENVIRONMENT_FILE=.env.test && \
	export TESTING=true && \
	poetry run coverage run -m pytest -v --disable-warnings --color=yes app/tests/ && \
	poetry run coverage report

.PHONY: clean-dev
clean-dev:
	@echo -n "Are you sure? [yes/N] (this will delete volumes) " && read ans && [ $${ans:-N} = yes ]
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down --volumes --remove-orphans

.PHONY: clean-session-data
clean-session-data:
	rm -rf secrets/telethon-202*.session

.PHONY: dev
dev: clean-session-data
	sysctl vm.overcommit_memory 2>/dev/null | grep -q 'vm.overcommit_memory = 1' || sudo sysctl vm.overcommit_memory=1
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
prod: clean-session-data
	sysctl vm.overcommit_memory 2>/dev/null | grep -q 'vm.overcommit_memory = 1' || sudo sysctl vm.overcommit_memory=1
	docker compose --env-file .env.prod build
	docker compose --env-file .env.prod up -d --remove-orphans
	docker buildx prune --keep-storage 30gb -f
	docker image prune -f
	docker system df

.PHONY: stop-prod
stop-prod:
	docker compose down
