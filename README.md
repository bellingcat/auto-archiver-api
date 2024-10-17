# Auto Archiver API

An api that uses celery workers to process URL archive requests via [bellingcat/auto-archiver](https://github.com/bellingcat/auto-archiver), it allows authentication via Google OAuth Apps and enables CORS, everything runs on docker but development can be done without docker (except for redis).


## Development
http://localhost:8004

requires `src/.env`

cd /src
<!-- * `pipenv install --editable ../../auto-archiver` -->
* console 1 - `docker compose up redis` optionally add `dashboard` for flower dashboard and `web` if not running uvicorn locally
* console 2 - `pipenv shell` + `celery worker --app=worker.celery --loglevel=info --logfile=logs/celery_dev.log`
  * `celery --app=worker.celery worker --loglevel=info --logfile=logs/celery_dev.log` celery 5
  * or with watchdog for dev auto-reload `watchmedo auto-restart -d ./  -- celery --app=worker.celery worker --loglevel=info --logfile=logs/celery_dev.log`
* console 3 - `pipenv shell` + `uvicorn main:app --host 0.0.0.0 --reload`
orchestration must be from the console(?)
* turn off VPNs if connection to docker is not working

## User management
Copy [example.user-groups.yaml](src/example.user-groups.yaml) into a new file and set the environment variable `USER_GROUPS_FILENAME` to that filename (defaults to `user-groups.yaml`).

This file contains 2 parts user-groups specifications. Each user can archive URLs publicly, privately, or privately for a group so long as they are declared as part of that group. In the example bellow `email1` has 2 groups while `email3` has none. 
```yaml
users:
  email1@example.com:
    - group1
    - group2
  email2@example.com:
    - group2
  email3@example-no-group.com:
```

Auto-archiver orchestrator files configurations. For each archiving task an orchestrator is chosen, either from a specified group (if group-level visibility) or the first group the user is assigned to in the above file or the `default` orchestration file which is a required config.
```yaml
orchestrators:
  group1: secrets/orchestration-group1.yaml
  group2: secrets/orchestration-group2.yaml
  default: secrets/orchestration-default:.yaml
```

## Database migrations
check https://alembic.sqlalchemy.org/en/latest/tutorial.html#the-migration-environment

* create migrations with `alembic revision -m "create account table"`
* migrate to most recent with `alembic upgrade head`
* downgrade with `alembic downgrade -1`

## Release
Update `main.py:VERSION`.

Copy `.env` and `src/.env` to deployment, along with the contents of `secrets/` including `secrets/orchestration.yaml`.

Then `make prod`.

#### updating packages/app/access
If pipenv packages are updated:  `make prod` to build images with new packages.

New users should be added to the `src/.env` file `ALLOWED_EMAILS` prop.

Run `pipenv update auto-archiver` inside `src` to update the auto-archiver version being used, then test with `make dev`. 


```bash
# CALL /sheet POST endpoint
curl -XPOST -H "Authorization: Bearer GOOGLE_OAUTH_TOKEN" -H "Content-type: application/json" -d '{"sheet_id": "SHEET_ID", "header": 1}' 'http://localhost:8004/sheet'

```