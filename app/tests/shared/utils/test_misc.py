from app.shared.utils.misc import fnv1a_hash_mod, get_all_urls


def test_fnv1a_hash_mod():
    # Test basic string hashing
    assert fnv1a_hash_mod("test", 10) == fnv1a_hash_mod("test", 10)
    assert 0 <= fnv1a_hash_mod("test", 10) < 10

    # Test different strings give different hashes
    assert fnv1a_hash_mod("test1", 100) != fnv1a_hash_mod("test2", 100)

    # Test different modulos
    hash1 = fnv1a_hash_mod("test", 5)
    hash2 = fnv1a_hash_mod("test", 10)
    assert 0 <= hash1 < 5
    assert 0 <= hash2 < 10

    # Test empty string
    assert isinstance(fnv1a_hash_mod("", 10), int)
    assert 0 <= fnv1a_hash_mod("", 10) < 10

    # Test long string
    long_str = "a" * 1000
    assert 0 <= fnv1a_hash_mod(long_str, 20) < 20

    # Test unicode string
    assert isinstance(fnv1a_hash_mod("测试", 10), int)
    assert 0 <= fnv1a_hash_mod("测试", 10) < 10

    # Test modulo = 1 edge case
    assert fnv1a_hash_mod("test", 1) == 0


def test_get_all_urls(db_session):
    from auto_archiver.core import Media, Metadata

    meta = Metadata().set_url("https://example.com")
    m1 = meta.add_media(Media("fn1.txt", urls=["outcome1.com"]))
    m2 = meta.add_media(Media("fn2.txt", urls=["outcome2.com"]))
    m3 = meta.add_media(Media("fn3.txt", urls=["outcome3.com"]))
    m1.set("screenshot", Media("screenshot.png", urls=["screenshot.com"]))
    m2.set(
        "thumbnails",
        [
            Media("thumb1.png", urls=["thumb1.com"]),
            Media("thumb2.png", urls=["thumb2.com"]),
        ],
    )
    m3.set("ssl_data", Media("ssl_data.txt", urls=["ssl_data.com"]).to_dict())
    m3.set("bad_data", {"bad": "dict is ignored"})

    urls = [u.url for u in get_all_urls(meta)]
    assert len(urls) == 7
    assert "outcome1.com" in urls
    assert "outcome2.com" in urls
    assert "outcome3.com" in urls
    assert "screenshot.com" in urls
    assert "thumb1.com" in urls
    assert "thumb2.com" in urls
    assert "ssl_data.com" in urls
