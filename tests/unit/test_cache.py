from galliard.cache import ImageCache


def test_put_and_get_roundtrip(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    data = b"\x89PNG\r\n\x1a\n" + b"payload" * 100
    cache.put("album1/track.mp3", data, "image/png")
    got = cache.get("album1/track.mp3")
    assert got is not None
    data_back, mime, _ = got
    assert data_back == data
    assert mime == "image/png"


def test_get_returns_none_for_unknown_uri(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    assert cache.get("never-seen.mp3") is None


def test_hash_deduplication(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    data = b"same bytes"
    cache.put("song-a.mp3", data, "image/jpeg")
    cache.put("song-b.mp3", data, "image/jpeg")
    # Both URIs resolve to the same underlying file.
    assert cache.get_cache_size() == len(data)


def test_two_distinct_payloads_stored_separately(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    cache.put("a.mp3", b"first", "image/jpeg")
    cache.put("b.mp3", b"secondary", "image/jpeg")
    assert cache.get_cache_size() == len(b"first") + len(b"secondary")


def test_clear_empties_cache(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    cache.put("x.mp3", b"data", "image/png")
    assert cache.get_cache_size() > 0
    cache.clear()
    assert cache.get_cache_size() == 0
    assert cache.get("x.mp3") is None


def test_broken_symlink_returns_none_and_cleans_up(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    cache.put("song.mp3", b"data", "image/jpeg")

    # Nuke the backing image file behind the symlink.
    for image_file in (tmp_path / "images").iterdir():
        image_file.unlink()

    # get() should clean up the dangling symlink and return None.
    assert cache.get("song.mp3") is None
    # The symlink's gone, so a subsequent put() can re-create it cleanly.
    cache.put("song.mp3", b"new data", "image/jpeg")
    got = cache.get("song.mp3")
    assert got is not None
    assert got[0] == b"new data"


def test_put_is_idempotent_for_same_uri(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    cache.put("song.mp3", b"first", "image/jpeg")
    cache.put("song.mp3", b"second", "image/jpeg")
    got = cache.get("song.mp3")
    assert got is not None
    assert got[0] == b"second"


def test_mime_type_controls_extension(tmp_path):
    cache = ImageCache(cache_dir=str(tmp_path))
    cache.put("a.mp3", b"png-ish", "image/png")
    cache.put("b.mp3", b"jpeg-ish", "image/jpeg")
    png_exts = list((tmp_path / "images").glob("*.png"))
    jpg_exts = list((tmp_path / "images").glob("*.jpg"))
    assert len(png_exts) == 1
    assert len(jpg_exts) == 1
