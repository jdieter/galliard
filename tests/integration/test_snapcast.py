"""SnapcastController: connect, client selection, volume round-trips."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def recording_conn(mpd_conn, monkeypatch):
    """MPDConn with recording emit + sync idle_add_once in all relevant modules."""
    import galliard.mpd_conn as mpd_conn_module
    import galliard.mpd_snapcast as mpd_snapcast_module

    calls = []
    mpd_conn.emit = lambda signal, *args: calls.append((signal, args))

    sync_idle = lambda fn, *a, **kw: fn(*a, **kw)
    monkeypatch.setattr(mpd_conn_module, "idle_add_once", sync_idle)
    monkeypatch.setattr(mpd_snapcast_module, "idle_add_once", sync_idle)

    mpd_conn.recorded = calls
    return mpd_conn


@pytest.fixture
def snapcast(recording_conn, fake_snapcast_server):
    """Freshly-constructed controller attached to the recording MPDConn."""
    from galliard.mpd_snapcast import SnapcastController

    return SnapcastController(recording_conn)


async def test_connect_selects_first_client_when_none_configured(
    snapcast, fake_snapcast_server, recording_conn
):
    recording_conn.config.set("snapcast.client_id", "")
    ok = await snapcast.connect()
    assert ok is True
    assert snapcast.client is fake_snapcast_server.clients[0]
    # Choice is persisted for next launch.
    assert recording_conn.config.get("snapcast.client_id") == "client-a"


async def test_connect_honours_configured_client_id(
    snapcast, fake_snapcast_server, recording_conn
):
    recording_conn.config.set("snapcast.client_id", "client-b")
    await snapcast.connect()
    assert snapcast.client is fake_snapcast_server.clients[1]


async def test_connect_falls_back_when_configured_client_missing(
    snapcast, fake_snapcast_server, recording_conn
):
    recording_conn.config.set("snapcast.client_id", "does-not-exist")
    await snapcast.connect()
    assert snapcast.client is fake_snapcast_server.clients[0]


async def test_get_clients_populates_list(
    snapcast, fake_snapcast_server, recording_conn
):
    ok = await snapcast.get_clients()
    assert ok is True
    assert [c["id"] for c in snapcast.clients] == ["client-a", "client-b"]


async def test_set_volume_sends_to_client_and_emits(
    snapcast, fake_snapcast_server, recording_conn
):
    await snapcast.connect()
    await snapcast.set_volume(42)
    snapcast.client.set_volume.assert_awaited_once_with(42)
    assert snapcast.volume == 42
    assert ("volume-changed", (42,)) in recording_conn.recorded


async def test_set_volume_lazy_connects_when_no_server(
    snapcast, fake_snapcast_server, recording_conn
):
    assert snapcast.server is None
    await snapcast.set_volume(10)
    # Autoconnected during set_volume.
    assert snapcast.server is fake_snapcast_server


async def test_get_volume_reads_from_selected_client(
    snapcast, fake_snapcast_server
):
    await snapcast.connect()
    snapcast.client.volume = 77
    v = await snapcast.get_volume()
    assert v == 77
    assert snapcast.volume == 77


async def test_available_flag_reflects_snapcast_availability(
    snapcast, monkeypatch
):
    """The ``available`` property flips with HAS_SNAPCAST."""
    import galliard.mpd_snapcast as snapcast_module

    monkeypatch.setattr(snapcast_module, "HAS_SNAPCAST", False)
    assert snapcast.available is False

    monkeypatch.setattr(snapcast_module, "HAS_SNAPCAST", True)
    assert snapcast.available is True
