"""Shared pytest fixtures and marker-based skip wiring for the test suite."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Marker-based skipping
# ---------------------------------------------------------------------------

def _mpd_available() -> bool:
    """True when an ``mpd`` binary is on $PATH."""
    return shutil.which("mpd") is not None


def _gtk_available() -> bool:
    """True when PyGObject + Gtk4 + libadwaita can be imported AND a display exists."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gtk, Adw  # noqa: F401
    except Exception:
        return False
    # Some widget constructors silently segfault without a usable display;
    # require either a real $DISPLAY / $WAYLAND_DISPLAY or Xvfb-style
    # offscreen rendering.
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return True


def pytest_collection_modifyitems(config, items):
    """Skip ``live_mpd``/``gtk`` tests cleanly when their prereqs are missing."""
    skip_live_mpd = pytest.mark.skip(reason="mpd binary not on PATH")
    skip_gtk = pytest.mark.skip(reason="Gtk4 / libadwaita not importable")
    mpd_ok = _mpd_available()
    gtk_ok = _gtk_available()
    for item in items:
        if "live_mpd" in item.keywords and not mpd_ok:
            item.add_marker(skip_live_mpd)
        if "gtk" in item.keywords and not gtk_ok:
            item.add_marker(skip_gtk)


# ---------------------------------------------------------------------------
# Temp XDG dirs
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_config_dir(monkeypatch, tmp_path):
    """Point Config at a throwaway dir for writes.

    ``galliard.config`` captures ``xdg.BaseDirectory.xdg_config_home`` at
    import time, so just setting ``$XDG_CONFIG_HOME`` isn't enough --
    rebind the captured name directly.
    """
    target = tmp_path / "config"
    target.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(target))
    import galliard.config as config_module

    monkeypatch.setattr(config_module, "xdg_config_home", str(target))
    return target


@pytest.fixture
def tmp_cache_dir(monkeypatch, tmp_path):
    """Point XDG_CACHE_HOME at a throwaway dir so ImageCache writes there."""
    target = tmp_path / "cache"
    target.mkdir()
    monkeypatch.setenv("XDG_CACHE_HOME", str(target))
    return target


# ---------------------------------------------------------------------------
# Fake MPD client for unit + mocked-integration tiers
# ---------------------------------------------------------------------------

def _make_fake_mpd_client() -> MagicMock:
    """Build a MagicMock shaped like ``mpd.asyncio.MPDClient``.

    Every command the app uses is stubbed as an ``AsyncMock`` with a
    sensible default return value. ``disconnect`` stays synchronous to
    match the real library. Tests override individual return values via
    ``client.status.return_value = {...}`` or similar.
    """
    client = MagicMock(name="FakeMPDClient")

    # Connection lifecycle.
    client.connect = AsyncMock(return_value=None)
    client.password = AsyncMock(return_value=None)
    client.disconnect = MagicMock(return_value=None)

    # Status + current-song.
    client.status = AsyncMock(return_value={})
    client.currentsong = AsyncMock(return_value={})

    # Library / search.
    client.list = AsyncMock(return_value=[])
    client.find = AsyncMock(return_value=[])
    client.search = AsyncMock(return_value=[])
    client.lsinfo = AsyncMock(return_value=[])
    client.playlistinfo = AsyncMock(return_value=[])
    client.listplaylists = AsyncMock(return_value=[])
    client.listplaylistinfo = AsyncMock(return_value=[])

    # Binary.
    client.readpicture = AsyncMock(return_value={})
    client.albumart = AsyncMock(return_value={})

    # Transport / playlist mutations.
    client.play = AsyncMock(return_value=None)
    client.pause = AsyncMock(return_value=None)
    client.stop = AsyncMock(return_value=None)
    client.next = AsyncMock(return_value=None)
    client.previous = AsyncMock(return_value=None)
    client.seekcur = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=None)
    client.clear = AsyncMock(return_value=None)
    client.add = AsyncMock(return_value=None)
    client.setvol = AsyncMock(return_value=None)
    client.random = AsyncMock(return_value=None)
    client.repeat = AsyncMock(return_value=None)
    client.single = AsyncMock(return_value=None)
    client.consume = AsyncMock(return_value=None)

    # The ``connected`` property on the real client returns True when
    # ``__run_task`` is live; we expose it as a simple attribute tests
    # can toggle directly.
    client.connected = True

    return client


@pytest.fixture
def fake_mpd_client():
    """Per-test ``mpd.asyncio.MPDClient`` stand-in."""
    return _make_fake_mpd_client()


# ---------------------------------------------------------------------------
# MPDConn under test
# ---------------------------------------------------------------------------

class _StubEventLoopPolicy:
    """Minimal stand-in for ``GLibEventLoopPolicy`` during unit tests.

    ``MPDConn.__init__`` calls ``policy.get_event_loop()`` and stashes
    the result on ``self.loop``. Under pytest we don't want to hijack
    the pytest-asyncio loop, so return the current one when there is
    one, otherwise fabricate a throwaway.
    """

    def get_event_loop(self):
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


@pytest.fixture
def mpd_conn(monkeypatch, tmp_config_dir, fake_mpd_client):
    """Construct an ``MPDConn`` wired to the fake client.

    ``MPDConn.__init__`` normally installs ``GLibEventLoopPolicy`` as
    the process-wide asyncio policy. That would steal pytest-asyncio's
    loop, so we replace it with a benign stub for the duration of the
    test.
    """
    from galliard import mpd_conn as mpd_conn_module

    monkeypatch.setattr(
        mpd_conn_module, "GLibEventLoopPolicy", _StubEventLoopPolicy,
    )
    # ``asyncio.set_event_loop_policy`` is still called inside __init__;
    # feed it something that won't break pytest-asyncio.
    monkeypatch.setattr(
        mpd_conn_module.asyncio,
        "set_event_loop_policy",
        lambda _policy: None,
    )

    from galliard.config import Config
    from galliard.mpd_conn import MPDConn

    config = Config()
    config.load()

    conn = MPDConn(config)
    conn.client = fake_mpd_client
    return conn


# ---------------------------------------------------------------------------
# Fake Snapcast server
# ---------------------------------------------------------------------------

def _make_fake_snapcast_client(identifier: str, friendly: str, volume: int = 50):
    """Build a mock with just the attributes :class:`SnapcastController` reads."""
    client = MagicMock()
    client.identifier = identifier
    client.friendly_name = friendly
    client.connected = True
    client.volume = volume
    client.set_volume = AsyncMock(return_value=None)
    return client


@pytest.fixture
def fake_snapcast_server(monkeypatch):
    """Patch ``snapcast.control.create_server`` to yield a scripted server.

    The returned server exposes a ``.clients`` list and a ``.stop()``
    method matching the real library. Tests may append / mutate clients
    via the returned ``server`` handle.
    """
    server = MagicMock(name="FakeSnapServer")
    server.clients = [
        _make_fake_snapcast_client("client-a", "Living Room"),
        _make_fake_snapcast_client("client-b", "Kitchen"),
    ]
    server.stop = MagicMock(return_value=None)

    async def _create_server(loop, host, port):
        return server

    import galliard.mpd_snapcast as snapcast_module

    monkeypatch.setattr(
        snapcast_module,
        "snapcast",
        MagicMock(control=MagicMock(create_server=_create_server)),
        raising=False,
    )
    monkeypatch.setattr(snapcast_module, "HAS_SNAPCAST", True)
    return server


# ---------------------------------------------------------------------------
# Tier 3: live MPD
# ---------------------------------------------------------------------------

def _free_tcp_port() -> int:
    """Ask the kernel for a currently-unused TCP port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_mpd_server(tmp_path):
    """Spawn a real ``mpd`` against ``tests/data/`` and yield ``(host, port)``.

    Writes a throwaway ``mpd.conf`` pointing ``music_directory`` at the
    repo's ``tests/data/`` tree, binds to a random local port, and kills
    the process on teardown.
    """
    if not _mpd_available():
        pytest.skip("mpd binary not on PATH")

    music_dir = Path(__file__).parent / "data"
    port = _free_tcp_port()

    conf = tmp_path / "mpd.conf"
    db_file = tmp_path / "mpd.db"
    log_file = tmp_path / "mpd.log"
    state_file = tmp_path / "mpd.state"
    conf.write_text(
        f"""
music_directory    "{music_dir}"
db_file            "{db_file}"
log_file           "{log_file}"
state_file         "{state_file}"
bind_to_address    "127.0.0.1"
port               "{port}"
audio_output {{
    type    "null"
    name    "null"
}}
""".strip()
    )

    proc = subprocess.Popen(
        ["mpd", "--no-daemon", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Poll the port until mpd is accepting connections (usually <100ms).
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        proc.kill()
        proc.wait()
        pytest.fail(f"mpd failed to start on port {port}")

    try:
        yield ("127.0.0.1", port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ---------------------------------------------------------------------------
# Tier 4: Gtk smoke
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _session_xdg_dirs(tmp_path_factory):
    """Pin XDG_CONFIG_HOME / XDG_CACHE_HOME to a session-wide tmp dir.

    Session-scoped so the singleton Galliard app (which constructs a
    ``Config`` in its ``__init__``) can't write to the developer's
    real ``~/.config/galliard/``. Repaired after multiple users
    reported their preferences being clobbered by the test run.
    """
    root = tmp_path_factory.mktemp("xdg")
    config_home = root / "config"
    config_home.mkdir()
    cache_home = root / "cache"
    cache_home.mkdir()

    os.environ["XDG_CONFIG_HOME"] = str(config_home)
    os.environ["XDG_CACHE_HOME"] = str(cache_home)

    # ``galliard.config`` caches xdg_config_home at import time, so env
    # vars alone aren't enough if anything has already imported it.
    try:
        import galliard.config as config_module

        config_module.xdg_config_home = str(config_home)
    except ImportError:
        pass

    return config_home, cache_home


@pytest.fixture(scope="session")
def _gtk_app_singleton(_session_xdg_dirs):
    """One-shot Galliard app for the whole session.

    Adw.Application registers its ID on the session DBus; constructing a
    second instance with the same ID in the same process errors with
    ``The application ID is already registered``. Scope it to ``session``
    and let per-test state ride on top via ``gtk_app``.
    """
    if not _gtk_available():
        pytest.skip("Gtk4 / libadwaita not importable")

    # Stub the asyncio-policy machinery so MPDConn.__init__ doesn't hijack
    # pytest-asyncio's loop. Done once here, persists for the session.
    from galliard import mpd_conn as mpd_conn_module

    mpd_conn_module.GLibEventLoopPolicy = _StubEventLoopPolicy
    mpd_conn_module.asyncio.set_event_loop_policy = lambda _p: None

    from galliard.app import Galliard

    app = Galliard()
    app.register()
    return app


@pytest.fixture
def gtk_app(_gtk_app_singleton, tmp_config_dir, fake_mpd_client):
    """Per-test handle to the session-wide Galliard, with a fresh fake client.

    Swaps in a fresh ``Config`` rooted at ``tmp_config_dir`` so any
    handlers that write config during a test (e.g. the preferences
    ``on_*_changed`` methods) don't pollute other tests or the
    developer's real settings.
    """
    from galliard.config import Config

    app = _gtk_app_singleton
    app.mpd_conn.config = Config()
    app.mpd_conn.config.load()
    app.mpd_conn.client = fake_mpd_client
    app.mpd_conn.connected = False
    app.mpd_conn.current_song = None
    app.mpd_conn.status = {}
    app.mpd_conn.prev_status = {}
    return app
