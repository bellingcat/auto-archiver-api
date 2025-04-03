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
