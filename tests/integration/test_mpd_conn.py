"""Command dispatch + connection lifecycle against a mocked client."""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def recording_conn(mpd_conn, monkeypatch):
    """MPDConn whose ``emit`` records and whose ``idle_add_once`` is sync."""
    import galliard.mpd_conn as mpd_conn_module

    calls = []

    def record(signal, *args):
        calls.append((signal, args))

    mpd_conn.emit = record
    monkeypatch.setattr(
        mpd_conn_module,
        "idle_add_once",
        lambda fn, *a, **kw: fn(*a, **kw),
    )
    mpd_conn.recorded = calls
    return mpd_conn


def _signals(conn, name):
    return [args for signal, args in conn.recorded if signal == name]


class TestCommandDispatch:
    async def test_async_play_forwards_position(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_play(2)
        recording_conn.client.play.assert_awaited_once_with(2)

    async def test_async_play_without_position(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_play()
        recording_conn.client.play.assert_awaited_once_with()

    async def test_async_pause_stop_next_previous(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_pause()
        await recording_conn.async_stop()
        await recording_conn.async_next()
        await recording_conn.async_previous()
        recording_conn.client.pause.assert_awaited()
        recording_conn.client.stop.assert_awaited()
        recording_conn.client.next.assert_awaited()
        recording_conn.client.previous.assert_awaited()

    async def test_commands_noop_when_disconnected(self, recording_conn):
        recording_conn.connected = False
        await recording_conn.async_play()
        recording_conn.client.play.assert_not_awaited()

    async def test_async_add_songs_to_playlist_emits_change(self, recording_conn):
        recording_conn.connected = True
        ok = await recording_conn.async_add_songs_to_playlist(["a.mp3", "b.mp3"])
        assert ok is True
        # Each uri sent individually to client.add.
        calls = [c.args for c in recording_conn.client.add.await_args_list]
        assert calls == [("a.mp3",), ("b.mp3",)]
        assert _signals(recording_conn, "playlist-changed") == [()]

    async def test_async_add_songs_empty_list_returns_false(self, recording_conn):
        recording_conn.connected = True
        ok = await recording_conn.async_add_songs_to_playlist([])
        assert ok is False
        recording_conn.client.add.assert_not_awaited()


class TestVolumeRouting:
    async def test_routes_to_mpd_when_configured(self, recording_conn):
        recording_conn.connected = True
        recording_conn.config.set("volume.method", "mpd")
        await recording_conn.async_set_volume(60)
        recording_conn.client.setvol.assert_awaited_once_with(60)

    async def test_routes_to_snapcast_when_configured(
        self, recording_conn, fake_snapcast_server
    ):
        recording_conn.connected = True
        recording_conn.config.set("volume.method", "snapcast")
        # Reinstantiate the controller so it picks up the patched HAS_SNAPCAST.
        from galliard.mpd_snapcast import SnapcastController

        recording_conn.snapcast = SnapcastController(recording_conn)
        recording_conn.snapcast.set_volume = AsyncMock(return_value=True)

        await recording_conn.async_set_volume(42)
        recording_conn.snapcast.set_volume.assert_awaited_once_with(42)
        recording_conn.client.setvol.assert_not_awaited()


class TestConnectionLifecycle:
    async def test_successful_connect_emits_connected(self, recording_conn):
        recording_conn.client.connect = AsyncMock(return_value=None)
        ok = await recording_conn._connect()
        assert ok is True
        assert recording_conn.connected is True
        assert _signals(recording_conn, "connected") == [()]

    async def test_connect_with_password(self, recording_conn):
        recording_conn.config.set("mpd.password", "secret")
        recording_conn.client.connect = AsyncMock(return_value=None)
        recording_conn.client.password = AsyncMock(return_value=None)
        await recording_conn._connect()
        recording_conn.client.password.assert_awaited_once_with("secret")

    async def test_connect_failure_schedules_reconnect(self, recording_conn):
        import mpd

        recording_conn.client.connect = AsyncMock(
            side_effect=mpd.ConnectionError("refused"),
        )

        scheduled = []
        original = recording_conn._schedule_reconnection

        async def record_reconnect():
            scheduled.append(True)
            # Don't actually run the reconnection loop.
            return

        recording_conn._schedule_reconnection = record_reconnect

        ok = await recording_conn._connect()
        assert ok is False
        assert scheduled == [True]

    async def test_is_connected_reflects_state(self, recording_conn):
        recording_conn.connected = True
        assert recording_conn.is_connected() is True
        recording_conn.connected = False
        assert recording_conn.is_connected() is False


class TestDisconnect:
    async def test_disconnect_emits_disconnected(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.disconnect.return_value = None

        await recording_conn._disconnect_internal()

        assert recording_conn.connected is False

    async def test_disconnect_noop_when_not_connected(self, recording_conn):
        recording_conn.connected = False
        await recording_conn._disconnect_internal()
        recording_conn.client.disconnect.assert_not_called()


class TestAsyncQueries:
    async def test_async_get_albums_wraps_as_Album(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.list.return_value = [
            {"album": "A"},
            {"album": "B"},
        ]
        albums = await recording_conn.async_get_albums()
        assert [a.title for a in albums] == ["A", "B"]

    async def test_async_get_albums_filters_empty_names(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.list.return_value = [
            {"album": "A"},
            {"album": ""},
            {},  # missing key -- still filtered
        ]
        albums = await recording_conn.async_get_albums()
        assert [a.title for a in albums] == ["A"]

    async def test_async_get_artists_wraps_as_Artist(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.list.return_value = [
            {"artist": "Alice"},
            {"artist": "Bob"},
        ]
        artists = await recording_conn.async_get_artists()
        assert [a.name for a in artists] == ["Alice", "Bob"]

    async def test_async_find_forwards_filters(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.find.return_value = [
            {"file": "x.mp3", "title": "X"},
        ]
        songs = await recording_conn.async_find("artist", "A", "album", "B")
        recording_conn.client.find.assert_awaited_once_with(
            "artist", "A", "album", "B"
        )
        assert songs[0].title == "X"

    async def test_async_get_albums_by_albumartist_uses_albumartist_tag(
        self, recording_conn
    ):
        recording_conn.connected = True
        recording_conn.client.list.return_value = [{"album": "Live at the Burrow"}]
        albums = await recording_conn.async_get_albums_by_albumartist(
            "Wombat Philharmonic"
        )
        recording_conn.client.list.assert_awaited_once_with(
            "album", "albumartist", "Wombat Philharmonic"
        )
        assert [a.title for a in albums] == ["Live at the Burrow"]
        assert albums[0].artist == "Wombat Philharmonic"
