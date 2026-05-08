from bacchus.ramdisk import ramdisk_size_bytes


def test_ramdisk_compress_encrypt_includes_overlap_margin() -> None:
    v = 1_000_000
    base_two_slabs = 2 * v * 1024 + (v * 1024) // 100
    overlap = (v // 4) * 1024
    assert ramdisk_size_bytes(v, True, True) == base_two_slabs + overlap


def test_ramdisk_compress_only_unchanged_from_one_slab_plus_slack() -> None:
    v = 100_000
    assert ramdisk_size_bytes(v, True, False) == v * 1024 + (v * 1024) // 100
