# Auto Archiver API

[![CI](https://github.com/bellingcat/auto-archiver-api/workflows/CI/badge.svg)](https://github.com/bellingcat/auto-archiver-api/actions/workflows/ci.yaml)

An api that uses celery workers to process URL archive requests via [bellingcat/auto-archiver](https://github.com/bellingcat/auto-archiver), it allows authentication via Google OAuth Apps and enables CORS, everything runs on docker but development can be done without docker (except for redis).


## User, Domains, Groups, and permissions management
there are 2 ways to access the API
1. via an API token which has full control/privileges to archive/search
2. via a Google Auth token which goes through the user access model

#### User access model
The permissions are defined solely via the `user-groups.yaml` file
- users belong to groups which determine their access level/quotas/orchestration setup
  - users are assigned to groups explicitly (via email)
  - users are assigned to groups implicitly (via email domains)
    - domains are associated to groups
  - users that are not explicitly or implicitly in the system belong to the `default` group, restrict their permissions if you do not wish them to be able to search/archive
  - if a user is assigned to one group which is not explicitly defined, a warning will be thrown, it may be necessary to do that if you discontinue a given group but the database still has entries for it and so
- groups determine
  - which orchestrator to use for single URL archives and for spreadsheet archives
  - a set of permissions
    - `read` can be [`all`], [] or a comma separated list of group names, meaning people in this group can access either all, none, or those belonging to explicitly listed groups.
      - the group itself must be included in the list, otherwise the user cannot search archives of that group
    - `archive_url` a boolean that enables the user to archive links in this group
    - `archive_sheet` a boolean that enables the user to archive spreadsheets
    - `sheet_frequency` a list of options for the sheet archiving frequency, currently max permissions is `["hourly", "daily"]`
    - `max_sheets` defines the maximum amount of spreadsheets someone can have in total (`-1` means no limit)
    - `max_archive_lifespan_months` defines the lifespan of an archive before being deleted from S3, users will be notified 1 month in advance with instructions to download TODO
    - `monthly_urls` how many total URLs someone can archive per month (`-1` means no limit)
    - `monthly_mbs` how many MBs of data someone can archive per month (`-1` means no limit)
    - `priority` one of `high` or `low`, this will be used to give archiving priority
  - group names are all lower-case


To figure out:
- workshop participants should be able to test this. `public`
- how can people bring their own storage/api keys?
- how to implement lifespan of archives? 6 months lifespan example. they should expect a way to download all archives locally.
- how to deactivate unused sheets and notify?
- how to mark URLs for deletion, and then do a hard delete?
- what actions can people take:
  - URL (P=needs permission, O=open)
    - P archive
    - P search
    - O find own links
    - DISABLED find by id
    - P delete archive (soft)
  - Sheets
    - P create a new sheet
    - O get my sheets
    - O delete a sheet
    - P archive a sheet now


## Development
http://localhost:8004

TODO: update .env file instructions, should use .env.prod and .env.dev and only use .env for always overwriting dev/prod settings.

requires `src/.env`

cd /src
<!-- * `pipenv install --editable ../../auto-archiver` -->
* console 1 - `docker compose up redis` optionally add `web` if not running uvicorn locally
* console 2 - `pipenv shell` + `celery worker --app=worker.celery --loglevel=info --logfile=logs/celery_dev.log`
  * `celery --app=worker.celery worker --loglevel=info --logfile=logs/celery_dev.log` celery 5
  * or with watchdog for dev auto-reload `watchmedo auto-restart -d ./  -- celery --app=worker.celery worker --loglevel=info --logfile=logs/celery_dev.log`
* console 3 - `pipenv shell` + `uvicorn main:app --host 0.0.0.0 --reload`
orchestration must be from the console(?)
* turn off VPNs if connection to docker is not working

## User management
TODO: update description and example
- users/domains/groups
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
  default: secrets/orchestration-default:orchestration.yaml
```

## Database migrations
check https://alembic.sqlalchemy.org/en/latest/tutorial.html#the-migration-environment

* create migrations with `alembic revision -m "create account table"`
* if running in the normal pipenv environment use `PIPENV_DOTENV_LOCATION=.env.alembic pipenv run` followed by:
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


### Testing
```bash
# can be done from top level but let's do it from the src folder for consistency with CI etc
cd src
# run tests and generate coverage
PYTHONPATH=. PIPENV_DOTENV_LOCATION=.env.test pipenv run coverage run -m pytest -vv --disable-warnings --color=yes tests/  && pipenv run coverage html

# get coverage report in command line
pipenv run coverage report

# get coverage HTML
pipenv run coverage html

# > open/run server on htmlcov/index.html to navigate through line coverage
```
