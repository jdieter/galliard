import json

from galliard.config import Config


def test_defaults_available_before_load(tmp_config_dir):
    config = Config()
    assert config.get("mpd.host") == "localhost"
    assert config.get("mpd.port") == 6600
    assert config.get("auto_connect") is True


def test_missing_key_returns_default(tmp_config_dir):
    config = Config()
    assert config.get("nonexistent", "fallback") == "fallback"


def test_nested_missing_key_returns_default(tmp_config_dir):
    config = Config()
    assert config.get("mpd.nonexistent", "fallback") == "fallback"
    assert config.get("top.level.missing", 99) == 99


def test_set_and_get_roundtrip(tmp_config_dir):
    config = Config()
    config.set("mpd.host", "example.com")
    assert config.get("mpd.host") == "example.com"


def test_dotted_set_creates_intermediate_dicts(tmp_config_dir):
    config = Config()
    config.set("a.b.c", 42)
    assert config.get("a.b.c") == 42
    assert config.get("a.b") == {"c": 42}


def test_simple_key_set_and_get(tmp_config_dir):
    config = Config()
    config.set("auto_connect", False)
    assert config.get("auto_connect") is False


def test_load_creates_file_when_missing(tmp_config_dir):
    config = Config()
    config.load()
    assert (tmp_config_dir / "galliard" / "config.json").exists()


def test_load_reads_existing_file(tmp_config_dir):
    galliard_dir = tmp_config_dir / "galliard"
    galliard_dir.mkdir()
    (galliard_dir / "config.json").write_text(
        json.dumps({"mpd": {"host": "remote.example", "port": 7000}})
    )
    config = Config()
    config.load()
    assert config.get("mpd.host") == "remote.example"
    assert config.get("mpd.port") == 7000


def test_corrupted_config_leaves_defaults(tmp_config_dir):
    galliard_dir = tmp_config_dir / "galliard"
    galliard_dir.mkdir()
    (galliard_dir / "config.json").write_text("not valid json {{{")
    config = Config()
    # Shouldn't raise; defaults remain in place.
    config.load()
    assert config.get("mpd.host") == "localhost"


def test_save_persists_changes(tmp_config_dir):
    config = Config()
    config.set("mpd.host", "persisted.example")

    # Fresh instance reads the saved file.
    fresh = Config()
    fresh.load()
    assert fresh.get("mpd.host") == "persisted.example"
