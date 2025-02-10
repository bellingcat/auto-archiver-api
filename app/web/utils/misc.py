import base64
from fastapi.encoders import jsonable_encoder

def custom_jsonable_encoder(obj):
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode('utf-8')
    return jsonable_encoder(obj)
