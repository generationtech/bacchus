from bacchus.ramdisk import ramdisk_size_bytes


def test_ramdisk_compress_encrypt_three_slabs_tmpfs() -> None:
    v = 1_000_000
    expected = 3 * v * 1024 + (v * 1024) // 100
    assert ramdisk_size_bytes(v, True, True) == expected


def test_ramdisk_compress_only_two_slabs_tmpfs() -> None:
    v = 100_000
    assert ramdisk_size_bytes(v, True, False) == 2 * v * 1024 + (v * 1024) // 100


def test_ramdisk_encrypt_only_two_slabs_tmpfs() -> None:
    v = 50_000
    assert ramdisk_size_bytes(v, False, True) == 2 * v * 1024 + (v * 1024) // 100


def test_ramdisk_max_chunk_kb_expands_both_stages() -> None:
    v = 100_000
    max_chunk = 2_000_000
    assert ramdisk_size_bytes(v, True, False, max_chunk_kb=max_chunk) == 2 * max_chunk * 1024 + (
        max_chunk * 1024
    ) // 100
