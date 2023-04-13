from functools import cache
from sqlalchemy.orm import Session, load_only
from loguru import logger
from . import models, schemas
import yaml


def get_task(db: Session, task_id: str):
    return base_query(db).filter(models.Archive.id == task_id).first()

def get_tasks(db: Session, skip: int = 0, limit: int = 100):
    return base_query(db).offset(skip).limit(limit).all()

def search_tasks_by_url(db: Session, url:str, skip: int = 0, limit: int = 100):
    return base_query(db).filter(models.Archive.url.like(f'%{url}%')).offset(skip).limit(limit).all()

def search_tasks_by_email(db: Session, email:str, skip: int = 0, limit: int = 100):
    return base_query(db).filter(models.Archive.author.has(email=email)).offset(skip).limit(limit).all()

def create_task(db: Session, task: schemas.TaskCreate):
    db_task = models.Archive(id=task.id, url=task.url, author=task.author, result=task.result)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

# def delete_task(db: Session, task_id: str, email:str)->bool:
#     db_task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.author==email).first()
#     if db_task:
#         db.delete(db_task)
#         db.commit()
#     return db_task is not None

def soft_delete_task(db: Session, task_id: str, email:str)->bool:
    db_task = db.query(models.Archive).filter(models.Archive.id == task_id, models.Archive.author==email, models.Archive.deleted==False).first()
    if db_task:
        db_task.deleted = True
        db.commit()
    return db_task is not None

def base_query(db:Session):
    # allow only some fields to be returned, for example author should remain hidden
    return db.query(models.Archive)\
        .options(load_only(models.Archive.id, models.Archive.created_at, models.Archive.url, models.Archive.result))\
        .filter(models.Archive.deleted == False)

@cache
def get_group(db:Session, group_name:str)->models.Group:
    db_group = db.query(models.Group).filter(models.Group.id==group_name).first()
    if db_group is None:
        db_group = models.Group(id=group_name)
        db.add(db_group)
    return db_group


def upsert_user_groups(db:Session, filename:str):
    """
    reads the user_groups yaml file and inserts any new users, groups, 
    along with new participation of users in groups
    """
    logger.debug("Updating user-groups configuration.")

    # read yaml safely
    with open(filename) as inf:
        try:
            user_groups_yaml = yaml.safe_load(inf)
        except yaml.YAMLError as e:
            logger.error(f"could not open user groups filename {filename}: {e}")
            raise e

    # upserting in DB
    user_groups = user_groups_yaml.get("users", {})
    logger.debug(f"Found {len(user_groups)} users.")
    db.query(models.association_table_user_groups).delete()

    for user_email, groups in user_groups.items():
        assert '@' in user_email, f'Invalid user email {user_email}'
        logger.info(f"email='{user_email[0:3]}...{user_email[-8:]}', {groups=}")
        db_user = db.query(models.User).filter(models.User.email==user_email).first()
        if db_user is None: 
            db_user = models.User(email=user_email)
            db.add(db_user)
        if not groups: continue # avoid hanging in for x in None:
        for group in groups:
            db_group = get_group(db, group)
            db_group.users.append(db_user)

    db.commit()
    count_user_groups = db.query(models.association_table_user_groups).count()
    logger.success(f"Completed refresh, now: {count_user_groups} user-groups relationships.")