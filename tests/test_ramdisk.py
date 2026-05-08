from bacchus.ramdisk import ramdisk_size_bytes


def test_ramdisk_compress_encrypt_includes_third_slab_for_tar_gz_peak() -> None:
    v = 1_000_000
    three_slabs = 3 * v * 1024 + (v * 1024) // 100
    assert ramdisk_size_bytes(v, True, True) == three_slabs


def test_ramdisk_compress_only_unchanged_from_one_slab_plus_slack() -> None:
    v = 100_000
    assert ramdisk_size_bytes(v, True, False) == v * 1024 + (v * 1024) // 100
