from typing import List

from auto_archiver.core import Media, Metadata

from app.shared.db import models
from app.shared.log import logger


def fnv1a_hash_mod(s: str, modulo: int) -> int:
    # receives a string and returns a number in [0:modulo-1], ensures an even
    # distribution over the modulo range
    offset_basis_hash = 0x811C9DC5  # FNV offset basis
    fnv_prime = 0x01000193  # FNV prime
    for char in s:
        offset_basis_hash ^= ord(char)
        offset_basis_hash *= fnv_prime
        offset_basis_hash &= 0xFFFFFFFF  # Keep it 32-bit
    return (
        offset_basis_hash
        if offset_basis_hash < 0x80000000
        else offset_basis_hash - 0x100000000
    ) % modulo


def convert_if_media(media):
    if isinstance(media, Media):
        return media
    elif isinstance(media, dict):
        try:
            return Media.from_dict(media)
        except Exception as e:
            logger.debug(f"error parsing {media} : {e}")
    return False


def get_all_urls(result: Metadata) -> List[models.ArchiveUrl]:
    db_urls = []
    for m in result.media:
        for i, url in enumerate(m.urls):
            db_urls.append(
                models.ArchiveUrl(url=url, key=m.get("id", f"media_{i}"))
            )
        for k, prop in m.properties.items():
            if prop_converted := convert_if_media(prop):
                for i, url in enumerate(prop_converted.urls):
                    db_urls.append(
                        models.ArchiveUrl(
                            url=url, key=prop_converted.get("id", f"{k}_{i}")
                        )
                    )
            if isinstance(prop, list):
                for i, prop_media in enumerate(prop):
                    if prop_media := convert_if_media(prop_media):
                        for j, url in enumerate(prop_media.urls):
                            db_urls.append(
                                models.ArchiveUrl(
                                    url=url,
                                    key=prop_media.get(
                                        "id", f"{k}{prop_media.key}_{i}.{j}"
                                    ),
                                )
                            )
    return db_urls
