from app.shared.utils.misc import fnv1a_hash_mod


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
