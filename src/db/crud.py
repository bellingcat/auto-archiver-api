from sqlalchemy.orm import Session, load_only
from loguru import logger
from . import models, schemas


def get_task(db: Session, task_id: str):
    return base_query(db).filter(models.Task.id == task_id).first()

def get_tasks(db: Session, skip: int = 0, limit: int = 100):
    return base_query(db).offset(skip).limit(limit).all()

def search_tasks_by_url(db: Session, url:str, skip: int = 0, limit: int = 100):
    return base_query(db).filter(models.Task.url.like(f'%{url}%')).offset(skip).limit(limit).all()

def search_tasks_by_email(db: Session, email:str, skip: int = 0, limit: int = 100):
    return base_query(db).filter(models.Task.author==email).offset(skip).limit(limit).all()

def base_query(db:Session):
    # allow only some fields to be returned, for example author should remain hidden
    return db.query(models.Task).options(load_only(models.Task.id, models.Task.created_at, models.Task.url, models.Task.result))

def create_task(db: Session, task: schemas.TaskCreate):
    db_task = models.Task(id=task.id, url=task.url, author=task.author, result=task.result)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def delete_task(db: Session, task_id: str, email:str)->bool:
    db_task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.author==email).first()
    if db_task:
        db.delete(db_task)
        db.commit()
    return db_task is not None