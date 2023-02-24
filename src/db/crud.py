from sqlalchemy.orm import Session
from loguru import logger

from . import models, schemas


def get_task(db: Session, task_id: str):
    return db.query(models.Task).filter(models.Task.id == task_id).first()


# def get_user_by_email(db: Session, email: str):
#     return db.query(models.User).filter(models.User.email == email).first()


def get_tasks(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Task).offset(skip).limit(limit).all()


def create_task(db: Session, task: schemas.TaskCreate):
    db_task = models.Task(id=task.id, url=task.url, author=task.author, result=task.result)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task
