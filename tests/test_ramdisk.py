from bacchus.ramdisk import ramdisk_size_bytes


def test_ramdisk_compress_encrypt_two_slabs_gzip_staged_on_dest() -> None:
    v = 1_000_000
    two_slabs = 2 * v * 1024 + (v * 1024) // 100
    assert ramdisk_size_bytes(v, True, True) == two_slabs


def test_ramdisk_compress_only_unchanged_from_one_slab_plus_slack() -> None:
    v = 100_000
    assert ramdisk_size_bytes(v, True, False) == v * 1024 + (v * 1024) // 100
