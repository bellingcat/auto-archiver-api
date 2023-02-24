## development
http://localhost:8004

requires `src/.env`

cd /src
* `pipenv install --editable ../../auto-archiver`
* console 1 - `docker compose up  web redis dashboard `
* console 2 - `pipenv shell` + `celery worker --app=worker.celery --loglevel=info --logfile=logs/celery_dev.log`
  * `celery --app=worker.celery worker --loglevel=info --logfile=logs/celery_dev.log` celery 5
* console 3 - `pipenv shell` + `uvicorn main:app --host 0.0.0.0 --reload`
orchestration must be from the console(?)

