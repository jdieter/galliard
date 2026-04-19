"""The status monitor loop: song-changed, playlist-changed, status emission."""

import asyncio

import pytest

from galliard.models import Song


@pytest.fixture
def recording_conn(mpd_conn, monkeypatch):
    """MPDConn with recording emit + synchronous idle_add_once."""
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


async def _run_monitor_once(conn, status, currentsong=None, playlistinfo=None):
    """Run a single monitor-loop iteration against scripted responses.

    The real loop is an infinite ``while``; we simulate one pass by
    driving the same internal calls in order so tests can assert on the
    emitted signals and state.
    """
    conn.client.status.return_value = status
    if currentsong is not None:
        conn.client.currentsong.return_value = currentsong

    # Mirror _monitor_status's key logic without the while / sleep.
    result = await conn._execute_command("status")
    if result:
        conn.status = result
        conn._emit_status_changes(result)
        current_song_id = result.get("songid")
        if current_song_id != getattr(conn, "_last_song_id", None):
            conn._last_song_id = current_song_id
            if current_song_id:
                song_data = await conn._execute_command("currentsong")
                if song_data:
                    conn.current_song = Song(**song_data)
                else:
                    conn.current_song = None
            else:
                conn.current_song = None
            conn.emit("song-changed")


async def test_song_change_wraps_current_song_as_Song(recording_conn):
    recording_conn.connected = True

    # Nothing -> playing A.
    await _run_monitor_once(
        recording_conn,
        status={"state": "play", "songid": "1"},
        currentsong={"file": "a.mp3", "title": "A"},
    )
    assert isinstance(recording_conn.current_song, Song)
    assert recording_conn.current_song.file == "a.mp3"
    assert recording_conn.current_song.title == "A"
    assert _signals(recording_conn, "song-changed") == [()]


async def test_song_change_fires_once_per_transition(recording_conn):
    recording_conn.connected = True

    await _run_monitor_once(
        recording_conn,
        status={"state": "play", "songid": "1"},
        currentsong={"file": "a.mp3"},
    )
    # Same songid again: no new song-changed.
    await _run_monitor_once(
        recording_conn,
        status={"state": "play", "songid": "1"},
        currentsong={"file": "a.mp3"},
    )
    # Different songid: one more song-changed.
    await _run_monitor_once(
        recording_conn,
        status={"state": "play", "songid": "2"},
        currentsong={"file": "b.mp3"},
    )
    assert len(_signals(recording_conn, "song-changed")) == 2
    assert recording_conn.current_song.file == "b.mp3"


async def test_stopping_clears_current_song(recording_conn):
    recording_conn.connected = True
    await _run_monitor_once(
        recording_conn,
        status={"state": "play", "songid": "1"},
        currentsong={"file": "a.mp3"},
    )
    assert recording_conn.current_song is not None

    # Stop: no songid in status.
    await _run_monitor_once(
        recording_conn,
        status={"state": "stop"},
    )
    assert recording_conn.current_song is None


async def test_status_changes_fire_alongside_song_change(recording_conn):
    recording_conn.connected = True
    await _run_monitor_once(
        recording_conn,
        status={"state": "play", "volume": "50", "songid": "1"},
        currentsong={"file": "a.mp3"},
    )
    assert _signals(recording_conn, "volume-changed") == [(50,)]
    assert _signals(recording_conn, "playback-status-changed") == [("play",)]
    assert _signals(recording_conn, "song-changed") == [()]
