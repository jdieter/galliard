"""Live MPD round-trips against tests/data/.

These gate on the ``mpd`` binary being on $PATH; the ``live_mpd_server``
fixture in ``conftest.py`` spins one up against a throwaway config
pointing at ``tests/data/`` and yields ``(host, port)``.
"""

import asyncio

import pytest

import mpd.asyncio


pytestmark = pytest.mark.live_mpd


async def _connected_client(host, port):
    """Open a raw python-mpd2 client and wait for it to finish the MPD hello."""
    client = mpd.asyncio.MPDClient()
    await client.connect(host, port)
    return client


async def test_fixture_starts_mpd(live_mpd_server):
    """The fixture exposes an accepting MPD on the yielded host/port."""
    host, port = live_mpd_server
    client = await _connected_client(host, port)
    try:
        # status() succeeds once the MPD hello has completed.
        result = await client.status()
        assert result is not None
    finally:
        client.disconnect()


async def test_library_lists_bundled_files(live_mpd_server):
    """MPD sees the three sample files we ship in tests/data/."""
    host, port = live_mpd_server
    client = await _connected_client(host, port)
    try:
        # Force a database update so MPD picks up the fixture directory.
        await client.update()
        # Give MPD a moment to scan the three tiny files.
        for _ in range(20):
            status = await client.status()
            if status.get("updating_db") is None:
                break
            await asyncio.sleep(0.1)

        files = await client.listall()
        # listall returns a flat list of {"directory": ...} and
        # {"file": ...} dicts. Pick out the files.
        file_paths = sorted(
            item["file"] for item in files if "file" in item
        )
    finally:
        client.disconnect()

    assert file_paths == ["test1.mp3", "test2.mp3", "test3.flac"]


async def test_mpdconn_connects_to_live_server(live_mpd_server, mpd_conn):
    """Our MPDConn wrapper talks successfully to a real MPD instance."""
    host, port = live_mpd_server
    mpd_conn.config.set("mpd.host", host)
    mpd_conn.config.set("mpd.port", port)
    # Swap the fake client out for a real one so _connect actually talks
    # to the fixture's mpd daemon.
    mpd_conn.client = mpd.asyncio.MPDClient()

    ok = await mpd_conn._connect()
    try:
        assert ok is True
        assert mpd_conn.is_connected() is True
    finally:
        if mpd_conn.is_connected():
            await mpd_conn._stop_monitoring_task()
            mpd_conn.client.disconnect()
            mpd_conn.connected = False


async def test_async_find_round_trips(live_mpd_server, mpd_conn):
    """``async_find`` returns Song objects for matching files."""
    host, port = live_mpd_server
    mpd_conn.config.set("mpd.host", host)
    mpd_conn.config.set("mpd.port", port)
    mpd_conn.client = mpd.asyncio.MPDClient()

    await mpd_conn._connect()
    try:
        # Force a DB update so find() can match anything.
        await mpd_conn.client.update()
        for _ in range(20):
            status = await mpd_conn.client.status()
            if status.get("updating_db") is None:
                break
            await asyncio.sleep(0.1)

        # find() with a file filter should round-trip.
        songs = await mpd_conn.async_find("file", "test1.mp3")
        assert len(songs) == 1
        assert songs[0].file == "test1.mp3"
    finally:
        if mpd_conn.is_connected():
            await mpd_conn._stop_monitoring_task()
            mpd_conn.client.disconnect()
            mpd_conn.connected = False
