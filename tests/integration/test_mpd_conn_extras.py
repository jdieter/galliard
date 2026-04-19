"""Extra MPDConn tests closing coverage gaps in reconnection, teardown,
binary fetches, and the less-common command wrappers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import mpd
import pytest


@pytest.fixture
def recording_conn(mpd_conn, monkeypatch):
    import galliard.mpd_conn as mpd_conn_module

    calls = []
    mpd_conn.emit = lambda signal, *args: calls.append((signal, args))
    monkeypatch.setattr(
        mpd_conn_module,
        "idle_add_once",
        lambda fn, *a, **kw: fn(*a, **kw),
    )
    mpd_conn.recorded = calls
    return mpd_conn


def _signals(conn, name):
    return [args for signal, args in conn.recorded if signal == name]


class TestSignalRegistration:
    def test_unknown_signal_raises_value_error(self, recording_conn):
        with pytest.raises(ValueError, match="Invalid signal name"):
            recording_conn.connect_signal("not-a-signal", lambda c: None)

    def test_non_callable_raises_type_error(self, recording_conn):
        with pytest.raises(TypeError, match="callable"):
            recording_conn.connect_signal("connected", "not-a-function")

    def test_disconnect_signal_with_none_handler_noops(self, recording_conn):
        # Should not raise when given a falsy handler id.
        recording_conn.disconnect_signal(None)
        recording_conn.disconnect_signal(0)

    def test_disconnect_signal_with_real_handler(self, recording_conn):
        handler = recording_conn.connect_signal("connected", lambda c: None)
        recording_conn.disconnect_signal(handler)


class TestExecuteCommandErrorPaths:
    async def test_mpd_error_schedules_reconnect_and_emits_signal(
        self, recording_conn
    ):
        """The 'Connection' substring shortcut in _execute_command relies on
        the exception's str() containing the word 'Connection'."""
        recording_conn.connected = True
        recording_conn.client.status = AsyncMock(
            side_effect=mpd.ConnectionError("Connection refused"),
        )

        scheduled = []

        async def _scheduler():
            scheduled.append(True)

        recording_conn._schedule_reconnection = _scheduler

        result = await recording_conn._execute_command("status")
        assert result is None
        # The reconnection task is spawned via create_task; yield so it runs.
        await asyncio.sleep(0)
        assert scheduled == [True]
        assert _signals(recording_conn, "connection-error") == [("Connection lost",)]

    async def test_non_connection_mpd_error_emits_error_text(
        self, recording_conn
    ):
        recording_conn.connected = True
        recording_conn.client.status = AsyncMock(
            side_effect=mpd.CommandError("bad command"),
        )

        async def _scheduler():
            pass

        recording_conn._schedule_reconnection = _scheduler

        await recording_conn._execute_command("status")
        # Non-"Connection" errors emit the raw error text.
        errors = _signals(recording_conn, "connection-error")
        assert any("bad command" in args[0] for args in errors)

    async def test_unexpected_error_logged_not_emitted(
        self, recording_conn, capsys
    ):
        recording_conn.connected = True
        recording_conn.client.status = AsyncMock(
            side_effect=ValueError("some other bug"),
        )
        result = await recording_conn._execute_command("status")
        assert result is None
        assert _signals(recording_conn, "connection-error") == []

    async def test_command_on_disconnected_client_short_circuits(
        self, recording_conn
    ):
        recording_conn.connected = False
        result = await recording_conn._execute_command("status")
        assert result is None
        recording_conn.client.status.assert_not_awaited()

    async def test_readpicture_vs_disconnect_race_is_silent(
        self, recording_conn, capsys
    ):
        """The 'NoneType has no attribute put' race is downgraded to debug."""
        recording_conn.connected = True
        # Simulate the post-disconnect state that triggers the race:
        # client.connected already False, readpicture raises AttributeError.
        recording_conn.client.connected = False
        recording_conn.client.readpicture = AsyncMock(
            side_effect=AttributeError(
                "'NoneType' object has no attribute 'put'"
            ),
        )
        result = await recording_conn._execute_command("readpicture", "song.mp3")
        assert result is None
        captured = capsys.readouterr()
        assert "Unexpected error" not in captured.out


class TestReconnectionLoop:
    async def test_schedule_reconnection_noop_when_task_active(
        self, recording_conn
    ):
        """A second schedule call while one is already queued is a no-op."""
        recording_conn.connected = True
        sentinel = MagicMock()
        sentinel.done.return_value = False
        recording_conn.reconnect_task = sentinel

        await recording_conn._schedule_reconnection()
        # No new task was created; the existing one is left alone.
        assert recording_conn.reconnect_task is sentinel

    async def test_reconnection_loop_exits_on_success(
        self, recording_conn, monkeypatch
    ):
        """One iteration of the reconnection loop succeeds and returns."""
        call_count = {"n": 0}

        async def _connect_stub(force_reconnect=False):
            call_count["n"] += 1
            recording_conn.connected = True
            return True

        recording_conn._connect = _connect_stub
        recording_conn.stop_reconnecting.clear()
        await recording_conn._reconnection_loop()
        assert call_count["n"] == 1

    async def test_reconnection_loop_stops_when_signaled(
        self, recording_conn
    ):
        """Setting stop_reconnecting during the loop breaks it cleanly."""

        async def _connect_stub(force_reconnect=False):
            return False

        recording_conn._connect = _connect_stub
        recording_conn.reconnect_interval = 0.05
        recording_conn.stop_reconnecting.clear()

        # Signal stop after a short delay so the loop exits.
        async def _stop_soon():
            await asyncio.sleep(0.1)
            recording_conn.stop_reconnecting.set()

        _stop_task = asyncio.create_task(_stop_soon())
        await asyncio.wait_for(recording_conn._reconnection_loop(), timeout=2.0)
        await _stop_task


class TestStopTasks:
    async def test_stop_monitoring_task_cancels_on_timeout(
        self, recording_conn
    ):
        """A hanging monitor task is force-cancelled after wait_for times out."""

        async def _hang():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        recording_conn.monitor_task = asyncio.create_task(_hang())
        # Give the task a moment to start blocking.
        await asyncio.sleep(0)

        await recording_conn._stop_monitoring_task()
        assert recording_conn.monitor_task is None

    async def test_stop_monitoring_task_waits_for_clean_exit(
        self, recording_conn
    ):
        """A monitor task that exits promptly on stop signal isn't cancelled."""
        exit_was_graceful = {"value": False}

        async def _respectful():
            try:
                await asyncio.wait_for(recording_conn.stop_monitoring.wait(), 5)
                exit_was_graceful["value"] = True
            except asyncio.TimeoutError:
                pass

        recording_conn.monitor_task = asyncio.create_task(_respectful())
        await asyncio.sleep(0)

        await recording_conn._stop_monitoring_task()
        assert exit_was_graceful["value"] is True

    async def test_stop_reconnection_task_cancels_on_timeout(
        self, recording_conn
    ):
        async def _hang():
            await asyncio.sleep(10)

        recording_conn.reconnect_task = asyncio.create_task(_hang())
        await asyncio.sleep(0)

        await recording_conn._stop_reconnection_task()
        assert recording_conn.reconnect_task.done()


class TestDisconnectFromServer:
    async def test_emits_disconnecting_blocked_and_disconnected(
        self, recording_conn
    ):
        recording_conn.connected = True

        async def _fake_disconnect():
            recording_conn.connected = False

        recording_conn._disconnect_internal = _fake_disconnect
        recording_conn.disconnect_from_server()

        for _ in range(10):
            await asyncio.sleep(0)

        signals = [s for s, _ in recording_conn.recorded]
        assert "disconnecting-blocked" in signals
        assert "disconnected" in signals

    async def test_noop_when_already_disconnected(self, recording_conn):
        recording_conn.connected = False
        recording_conn.disconnect_from_server()
        assert recording_conn.recorded == []

    def test_connect_to_server_returns_when_already_connected(
        self, recording_conn
    ):
        recording_conn.connected = True
        result = recording_conn.connect_to_server()
        assert result is True


class TestAlbumArtFetch:
    async def test_returns_cache_hit_without_querying(
        self, recording_conn, monkeypatch
    ):
        recording_conn.connected = True
        cached = (b"png bytes", "image/png", "/cache/foo.png")
        monkeypatch.setattr(
            recording_conn.image_cache, "get", lambda uri: cached
        )
        got = await recording_conn.async_get_album_art("song.mp3")
        assert got == cached
        recording_conn.client.readpicture.assert_not_awaited()

    async def test_reads_picture_on_cache_miss(
        self, recording_conn, monkeypatch
    ):
        recording_conn.connected = True
        monkeypatch.setattr(recording_conn.image_cache, "get", lambda uri: None)
        recording_conn.client.readpicture = AsyncMock(
            return_value={"binary": b"new", "mime": "image/jpeg"},
        )
        monkeypatch.setattr(
            recording_conn.image_cache, "put",
            lambda uri, data, mime: "/cache/stored",
        )
        got = await recording_conn.async_get_album_art("song.mp3")
        assert got == (b"new", "image/jpeg", "/cache/stored")

    async def test_returns_empty_triple_for_empty_uri(self, recording_conn):
        recording_conn.connected = True
        assert await recording_conn.async_get_album_art("") == (
            None, None, None,
        )

    async def test_returns_empty_triple_when_disconnected(self, recording_conn):
        recording_conn.connected = False
        assert await recording_conn.async_get_album_art("song.mp3") == (
            None, None, None,
        )

    async def test_readpicture_error_returns_empty_triple(
        self, recording_conn, monkeypatch
    ):
        recording_conn.connected = True
        monkeypatch.setattr(recording_conn.image_cache, "get", lambda uri: None)
        recording_conn.client.readpicture = AsyncMock(
            side_effect=RuntimeError("boom"),
        )
        assert await recording_conn.async_get_album_art("song.mp3") == (
            None, None, None,
        )


class TestSongDetails:
    async def test_returns_song_for_match(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.find = AsyncMock(
            return_value=[{"file": "a.mp3", "title": "A"}],
        )
        song = await recording_conn.async_get_song_details("a.mp3")
        assert song is not None
        assert song.title == "A"

    async def test_returns_none_for_empty_result(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.find = AsyncMock(return_value=[])
        assert await recording_conn.async_get_song_details("missing") is None

    async def test_returns_none_when_disconnected(self, recording_conn):
        recording_conn.connected = False
        assert await recording_conn.async_get_song_details("a.mp3") is None

    async def test_empty_path_returns_none(self, recording_conn):
        recording_conn.connected = True
        assert await recording_conn.async_get_song_details("") is None


class TestDirectoryListing:
    async def test_lsinfo_round_trips(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.lsinfo = AsyncMock(
            return_value=[{"directory": "Albums"}, {"file": "a.mp3"}],
        )
        result = await recording_conn.async_list_directory("")
        assert len(result) == 2

    async def test_empty_when_disconnected(self, recording_conn):
        recording_conn.connected = False
        assert await recording_conn.async_list_directory("Albums") == []

    async def test_exception_returns_empty(self, recording_conn, capsys):
        recording_conn.connected = True
        recording_conn.client.lsinfo = AsyncMock(
            side_effect=RuntimeError("kaboom"),
        )
        result = await recording_conn.async_list_directory("Albums")
        assert result == []


class TestExtraCommands:
    async def test_async_seek(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_seek(30)
        recording_conn.client.seekcur.assert_awaited_once_with(30)

    async def test_async_delete(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_delete(5)
        recording_conn.client.delete.assert_awaited_once_with(5)

    async def test_async_clear_playlist(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_clear_playlist()
        recording_conn.client.clear.assert_awaited_once()

    async def test_async_set_random(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_set_random("1")
        recording_conn.client.random.assert_awaited_once_with("1")

    async def test_async_set_random_noop_when_disconnected(self, recording_conn):
        recording_conn.connected = False
        await recording_conn.async_set_random("1")
        recording_conn.client.random.assert_not_awaited()

    async def test_async_set_repeat(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_set_repeat("1")
        recording_conn.client.repeat.assert_awaited_once_with("1")

    async def test_async_set_single(self, recording_conn):
        recording_conn.connected = True
        await recording_conn.async_set_single("0")
        recording_conn.client.single.assert_awaited_once_with("0")

    async def test_async_toggle_consume_flips_bit(self, recording_conn):
        recording_conn.connected = True
        recording_conn.status = {"consume": "0"}
        await recording_conn.async_toggle_consume()
        recording_conn.client.consume.assert_awaited_once_with(1)

    async def test_async_toggle_consume_from_on(self, recording_conn):
        recording_conn.connected = True
        recording_conn.status = {"consume": "1"}
        await recording_conn.async_toggle_consume()
        recording_conn.client.consume.assert_awaited_once_with(0)


class TestSearchAndQueries:
    async def test_async_search(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.search = AsyncMock(
            return_value=[{"file": "a.mp3", "title": "A"}],
        )
        songs = await recording_conn.async_search("artist", "foo")
        assert songs[0].title == "A"
        recording_conn.client.search.assert_awaited_once_with("artist", "foo")

    async def test_async_search_disconnected(self, recording_conn):
        recording_conn.connected = False
        assert await recording_conn.async_search("artist", "foo") == []

    async def test_async_get_current_playlist(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.playlistinfo = AsyncMock(
            return_value=[{"file": "x.mp3"}, {"file": "y.mp3"}],
        )
        songs = await recording_conn.async_get_current_playlist()
        assert [s.file for s in songs] == ["x.mp3", "y.mp3"]

    async def test_async_get_stored_playlists(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.listplaylists = AsyncMock(
            return_value=[{"playlist": "Chill"}, {"playlist": "Energy"}],
        )
        result = await recording_conn.async_get_stored_playlists()
        assert len(result) == 2

    async def test_async_get_playlist_songs(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.listplaylistinfo = AsyncMock(
            return_value=[{"file": "a.mp3"}],
        )
        songs = await recording_conn.async_get_playlist_songs("Chill")
        assert [s.file for s in songs] == ["a.mp3"]

    async def test_async_get_songs_by_artist(self, recording_conn):
        recording_conn.connected = True
        recording_conn.client.find = AsyncMock(
            return_value=[{"file": "a.mp3"}],
        )
        songs = await recording_conn.async_get_songs_by_artist("Alice")
        assert len(songs) == 1


class TestReadpicturePriority:
    """Binary commands use the low-priority semaphore."""

    async def test_readpicture_uses_low_priority_semaphore(
        self, recording_conn
    ):
        recording_conn.connected = True
        recording_conn.client.readpicture = AsyncMock(return_value={})

        # Acquire the entire low-priority pool; readpicture should block.
        for _ in range(5):
            await recording_conn.low_prio_cmd_sem.acquire()

        async def _fetch():
            # high-prio sem has 50 slots so this shouldn't be the blocker.
            return await recording_conn._execute_command(
                "readpicture", "x.mp3",
            )

        task = asyncio.create_task(_fetch())
        # Give the task a chance to block; it shouldn't complete yet.
        await asyncio.sleep(0.05)
        assert not task.done()

        # Release one slot; the task proceeds.
        recording_conn.low_prio_cmd_sem.release()
        await asyncio.wait_for(task, timeout=1.0)

        # Release the others to avoid leaking state.
        for _ in range(4):
            recording_conn.low_prio_cmd_sem.release()
