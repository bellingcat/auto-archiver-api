# Auto Archiver API

[![CI](https://github.com/bellingcat/auto-archiver-api/workflows/CI/badge.svg)](https://github.com/bellingcat/auto-archiver-api/actions/workflows/ci.yaml)

A web API that uses celery workers to process URL archive requests via [bellingcat/auto-archiver](https://github.com/bellingcat/auto-archiver), it allows authentication via Google OAuth Apps and enables CORS, everything runs on docker.

![image](https://github.com/user-attachments/assets/905d697d-b83e-437b-87d1-cc86d3c8d8bf)

## setup
To properly set up the API you need to install `docker` and to have these files, see more on the sections below:
1. a `.env.prod` and `.env.dev` to configure the API, stays at the root level
2. a `user-groups.yaml` to manage user permissions
  1. note that all local files referenced in `user-groups.yaml` and any orchestration.yaml files should be relative to the home directory so if your service account is in `secrets/orchestration.yaml` use that path and not just `orchestration.yaml`.
  2. go through the example file and configure it according to your needs.
3. you will need to create and reference at least one `secrets/orchestration.yaml` file, you can do so by following the instructions in the [auto-archiver](https://github.com/bellingcat/auto-archiver#installation) that automatically generates one for you. If you use the archive sheets feature you will need to create a `orchestrationsheets-sheets.yaml` file as well that should have the `gsheet_feeder_db` feeder and database enabled and configured, the auto-archiver has [extensive documentation](https://auto-archiver.readthedocs.io/en/latest/) on how to set this up.

Do not commit those files, they are .gitignored by default.
We also advise you to keep any sensitive files in the `secrets/` folder which is pinned and gitignored.

We have examples for both of those files (`.env.example` and `user-groups.example.yaml`), and here's how to set them up whether you're in development or production:

### setup for DEVELOPMENT
```bash
# copy and modify the .env.dev file according to your needs
cp .env.example .env.dev
# copy the user-groups.example.yaml and modify it accordingly
cp user-groups.example.yaml user-groups.dev.yaml
# run the APP, make sure VPNs are off
make dev
# check it's running by calling the health endpoint
curl 'http://localhost:8004/health'
# > {"status":"ok"}
```
now go to http://localhost:8004/docs#/ and you should see the API documentation

### setup for PRODUCTION
```bash
# copy and modify the .env.prod file according to your needs
cp .env.example .env.prod
# copy the user-groups.example.yaml and modify it accordingly
cp user-groups.example.yaml user-groups.yaml
# deploy the app
make prod
# check it's running by calling the health endpoint
curl 'http://localhost:8004/health'
# > {"status":"ok"}
```
now go to http://localhost:8004/docs#/ and you should see the API documentation

## User, Domains, Groups, and permissions management
there are 2 ways to access the API
1. via an API token which has full control/privileges to archive/search
2. via a Google Auth token which goes through the user access model

#### User access model
The permissions are defined solely via the `user-groups.yaml` file
- users belong to groups which determine their access level/quotas/orchestration setup
  - users are assigned to groups explicitly (via email)
  - users are assigned to groups implicitly (via email domains) as domains can be associated to groups
  - users that are not explicitly or implicitly in the system belong to the `default` group, restrict their permissions if you do not wish them to be able to search/archive
  - if a user is assigned to one group which is not explicitly defined, a warning will be thrown, it may be necessary to do that if you discontinue a given group but the database still has entries for it and so
- groups determine
  - which orchestrator to use for single URL archives and for spreadsheet archives see [GroupPermissions](app/shared/user_groups.py)
  - a set of permissions
    - `read` can be [`all`], [] or a comma separated list of group names, meaning people in this group can access either all, none, or those belonging to explicitly listed groups.
      - the group itself must be included in the list, otherwise the user cannot search archives of that group
    - `read_public` a boolean that enables the user to search public archives
    - `archive_url` a boolean that enables the user to archive links in this group
    - `archive_sheet` a boolean that enables the user to archive spreadsheets
    - `manually_trigger_sheet` a boolean that enables the user to manually trigger a sheet archive for sheets in this group
    - `sheet_frequency` a list of options for the sheet archiving frequency, currently max permissions is `["hourly", "daily"]`
    - `max_sheets` defines the maximum amount of spreadsheets someone can have in total (`-1` means no limit)
    - `max_archive_lifespan_months` defines the lifespan of an archive before being deleted from S3, users will be notified 1 month in advance with instructions to download TODO
    - `max_monthly_urls` how many total URLs someone can archive per month (`-1` means no limit)
    - `max_monthly_mbs` how many MBs of data someone can archive per month (`-1` means no limit)
    - `priority` one of `high` or `low`, this will be used to give archiving priority
  - group names are all lower-case


## development of web/worker without docker

<!-- * `pipenv install --editable ../../auto-archiver` -->
We advise you to use `make prod` but you can also spin up redis and run the API (uvicorn) and worker (celery) individually like so:
* console 1 - `make dev-redis-only` to spin up redis, turn off any VPNs
* console 2 - `export ENVIRONMENT_FILE=.env.dev` then `poetry run celery --app=app.worker.main.celery worker --loglevel=debug --logfile=/aa-api/logs/celery.log -Q high_priority,low_priority --concurrency=1`
  * or with watchdog for dev auto-reload `watchmedo auto-restart --patterns="*.py" --recursive --ignore-directories -- celery -- --app=app.worker.main.celery worker --loglevel=debug --logfile=/aa-api/logs/celery.log -Q high_priority,low_priority --concurrency=1`
* console 3 - `export ENVIRONMENT_FILE=.env.dev` then `poetry run uvicorn main:app --host 0.0.0.0 --reload`


## Database migrations
check https://alembic.sqlalchemy.org/en/latest/tutorial.html#the-migration-environment
```bash
# set the env variables
export ENVIRONMENT_FILE=.env.alembic
# create a new migration with description in app/migrations
poetry run alembic revision -m "create account table"
# perform all migrations
poetry run alembic upgrade head
# downgrade by one migration
poetry run alembic downgrade -1
```

## Release
Update the version in [config.py](app/web/config.py)

Make sure environment and user-groups files are up to date.

Then `make prod`.


## Development
```bash
# make sure all development dependencies are installed
poetry install --with dev

# this project uses pre-commit to enforce code style and formatting, set that up locally
poetry run pre-commit install

# you can test pre-commit with
poetry run pre-commit run --all-files

# this means pre-commit will always run with git commit, to skip it use
git commit --no-verify

# see the Makefile for more commands, but linting and formatting can be done with
make lint

# run all tests
make test
```

### Testing
```bash
# set the testing environment variables
export ENVIRONMENT_FILE=.env.test
# run tests and generate coverage
poetry run coverage run -m pytest -vv --disable-warnings --color=yes app/tests/
# get coverage report in command line
poetry run coverage report
# get coverage report in HTML format
poetry run coverage html
```
