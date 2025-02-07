import base64
from fastapi.encoders import jsonable_encoder

def custom_jsonable_encoder(obj):
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode('utf-8')
    return jsonable_encoder(obj)

def fnv1a_hash_mod(s: str, modulo:int) -> int:
    # receives a string and returns a number in [0:modulo-1], ensures an even distribution over the modulo range
    hash = 0x811c9dc5 # FNV offset basis
    fnv_prime = 0x01000193 # FNV prime
    for char in s:
        hash ^= ord(char)
        hash *= fnv_prime
        hash &= 0xFFFFFFFF # Keep it 32-bit
    return (hash if hash < 0x80000000 else hash - 0x100000000) % modulo