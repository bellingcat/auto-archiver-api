from celery.result import AsyncResult
from fastapi import Body, FastAPI, Form, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic.json import pydantic_encoder


from worker import create_task, create_archive_task, celery


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")



@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("home.html", context={"request": request})


@app.post("/tasks", status_code=201)
def run_task(payload = Body(...)):
    # task_type = payload["type"]
    # task = create_task.delay(int(task_type))
    task = create_archive_task.delay(payload["url"])
    return JSONResponse({"task_id": task.id})


@app.get("/tasks/{task_id}")
def get_status(task_id):
    task_result = AsyncResult(task_id, app=celery)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result
    }
    try:
        json_result = jsonable_encoder(result, custom_encoder=pydantic_encoder)
        return JSONResponse(json_result)#content=json_result)
    except Exception as e:
        print(e)
        print(task_result.result)
        return JSONResponse({
            "task_id": task_id,
            "task_status": "FAILURE",
        })
