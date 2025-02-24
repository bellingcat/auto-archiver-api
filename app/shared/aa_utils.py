# TODO: code in this file should eventually be moved to the auto-archiver code base

from typing import List

from auto_archiver.core import Media, Metadata
from loguru import logger

from app.shared.db import models


def get_all_urls(result: Metadata) -> List[models.ArchiveUrl]:
    db_urls = []
    for m in result.media:
        for i, url in enumerate(m.urls): db_urls.append(models.ArchiveUrl(url=url, key=m.get("id", f"media_{i}")))
        for k, prop in m.properties.items():
            if prop_converted := convert_if_media(prop):
                for i, url in enumerate(prop_converted.urls): db_urls.append(models.ArchiveUrl(url=url, key=prop_converted.get("id", f"{k}_{i}")))
            if isinstance(prop, list):
                for i, prop_media in enumerate(prop):
                    if prop_media := convert_if_media(prop_media):
                        for j, url in enumerate(prop_media.urls):
                            db_urls.append(models.ArchiveUrl(url=url, key=prop_media.get("id", f"{k}{prop_media.key}_{i}.{j}")))
    return db_urls



def convert_if_media(media):
    if isinstance(media, Media): return media
    elif isinstance(media, dict):
        try: return Media.from_dict(media)
        except Exception as e:
            logger.debug(f"error parsing {media} : {e}")
    return False
