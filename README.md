# Auto Archiver API

An api that uses celery workers to process URL archive requests via [bellingcat/auto-archiver](), it allows authentication via Google OAuth Apps an d enables CORS, everything runs on docker but development can be done without docker (except for redis).


## Development
http://localhost:8004

requires `src/.env`

cd /src
<!-- * `pipenv install --editable ../../auto-archiver` -->
* console 1 - `docker compose up redis` optionally add `dashboard` for flower dashboard and `web` if not running uvicorn locally
* console 2 - `pipenv shell` + `celery worker --app=worker.celery --loglevel=info --logfile=logs/celery_dev.log`
  * `celery --app=worker.celery worker --loglevel=info --logfile=logs/celery_dev.log` celery 5
* console 3 - `pipenv shell` + `uvicorn main:app --host 0.0.0.0 --reload`
orchestration must be from the console(?)
* turn off VPNs if connection to docker is not working


## Release
Copy `.env` and `src/.env` to deployment, along with the contents of `secrets/` including `secrets/orchestration.yaml`.

Then `docker compose up -d`.

#### updating packages/app
If pipenv packages are updated: `pipenv lock --requirements -r  > requirements.txt` (manually comment line `-i https://pypi.org/simple`) and then `docker compose down` + `docker compose up --build -d` to build images with new packages.