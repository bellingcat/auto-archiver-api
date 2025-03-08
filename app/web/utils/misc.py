import base64

from fastapi.encoders import jsonable_encoder


def custom_jsonable_encoder(obj) -> str:
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    return jsonable_encoder(obj)


def convert_priority_to_queue_dict(priority: str) -> dict:
    return {
        "priority": 0 if priority == "high" else 10,
        "queue": f"{priority}_priority",
    }
