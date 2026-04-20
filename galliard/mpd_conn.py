#!/usr/bin/env python3

import time
import socket
import asyncio
import logging
import hashlib
from typing import Any

from gi.repository import GLib, GObject
from gi.events import GLibEventLoopPolicy
from galliard.models import Song, Album, Artist
from galliard.cache import ImageCache
from galliard.utils.glib import idle_add_once

try:
    import mpd.asyncio
except ImportError:
    logging.error("python-mpd2 library with asyncio not found.")
    logging.error("Please install it with: pip install python-mpd2")
    exit(1)

from galliard.mpd_snapcast import HAS_SNAPCAST, SnapcastController  # noqa: E402


class MPDConn(GObject.Object):
    """MPD client connection wrapper with GObject integration using asyncio"""

    __gsignals__ = {
        "connecting-blocked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "connecting": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "connected": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "disconnecting-blocked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "disconnected": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "connection-error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "song-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "playlist-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # Granular status change signals
        "volume-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "playback-status-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "elapsed-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "repeat-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool, bool)),
        "random-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "single-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "consume-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "audio-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (
                str,
                int,
                int,
            ),
        ),  # format, sample rate, bits
        "bitrate-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, config):
        """Prepare MPD client state; no network I/O until ``connect_to_server``."""
        super().__init__()
        self.config = config
        self.client = mpd.asyncio.MPDClient()
        self.connected = False
        self.current_song = None
        self.status = {}
        self.prev_status = {}

        # Run asyncio on the GLib main loop so coroutine callbacks are
        # already on the UI thread -- no idle_add marshalling needed
        # inside async code.
        policy = GLibEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        self.loop = policy.get_event_loop()

        self.monitor_task = None
        self.stop_monitoring = asyncio.Event()

        self.reconnect_task = None
        self.stop_reconnecting = asyncio.Event()
        self.reconnect_interval = 5  # seconds between reconnection attempts
        self.auto_reconnect = True

        # Two semaphores so bulk low-priority commands (e.g. readpicture
        # during a library scroll) can't starve interactive ones.
        self.high_prio_cmd_sem = asyncio.Semaphore(50)
        self.low_prio_cmd_sem = asyncio.Semaphore(5)

        self.snapcast = SnapcastController(self)
        self.image_cache = ImageCache()

    async def _execute_command(self, cmd, *args, **kwargs) -> Any:
        """Run ``cmd`` against the MPD client under a concurrency semaphore.

        Connection errors trigger a reconnection task and emit
        ``connection-error``. Other MPD errors surface via the same
        signal but don't reconnect. Returns the command result or None
        on error.
        """
        if not self.connected and cmd != "connect":
            return None

        priority = True
        if cmd in ["readpicture",]:
            priority = False
        async with (self.high_prio_cmd_sem if priority == True else self.low_prio_cmd_sem):
            try:
                if cmd == "connect":
                    host, port, timeout, password = args
                    # python-mpd2's async MPDClient.connect is
                    # (host, port, loop=None) -- no timeout arg. Enforce
                    # the user-configured timeout via wait_for so slow
                    # / hung servers don't block indefinitely.
                    await asyncio.wait_for(
                        self.client.connect(host, port),
                        timeout=timeout,
                    )
                    if password:
                        await self.client.password(password)  # type: ignore
                    return True
                else:
                    func = getattr(self.client, cmd)
                    result = await func(*args, **kwargs)
                    return result
            except (
                mpd.MPDError,
                socket.error,
                ConnectionError,
                BrokenPipeError,
                OSError,
            ) as e:
                logging.error("MPD error: %s", e)
                asyncio.create_task(self._schedule_reconnection())
                if "Connection" in str(e):
                    idle_add_once(self.emit, "connection-error", "Connection lost")
                else:
                    idle_add_once(self.emit, "connection-error", str(e))
                return None
            except Exception as e:
                # python-mpd2's disconnect() synchronously sets its internal
                # __command_queue to None, so any command in flight (notably
                # the chunked readpicture) crashes with AttributeError when
                # it next tries to ``put`` onto the queue. That's a harmless
                # race -- log at debug so it doesn't spam stdout.
                if not self.client.connected:
                    logging.debug(f"{cmd} aborted mid-flight by disconnect: {e}")
                    return None
                logging.error("Unexpected error executing %s: %s", cmd, e)
                return None

    def connect_signal(self, signal_name, callback_func, *user_data):
        """Attach ``callback_func`` to ``signal_name``, returning the handler id.

        Raises :class:`ValueError` for unknown signal names so typos fail
        loudly rather than silently not firing.
        """
        valid_signals = [
            "connected",
            "connecting",
            "connecting-blocked",
            "disconnected",
            "disconnecting-blocked",
            "connection-error",
            "state-changed",
            "song-changed",
            "playlist-changed",
            "volume-changed",
            "playback-status-changed",
            "elapsed-changed",
            "repeat-changed",
            "random-changed",
            "single-changed",
            "consume-changed",
            "audio-changed",
            "bitrate-changed",
        ]

        if signal_name not in valid_signals:
            raise ValueError(
                f"Invalid signal name: {signal_name}. "
                f"Valid signals are: {', '.join(valid_signals)}"
            )

        if not callable(callback_func):
            raise TypeError("Callback must be a callable function")

        handler_id = super().connect(signal_name, callback_func, *user_data)
        return handler_id

    def disconnect_signal(self, handler_id):
        """Detach a handler previously returned by :meth:`connect_signal`."""
        if handler_id:
            super().disconnect(handler_id)

    async def _connect(self, force_reconnect=False):
        """Open the MPD connection, start the status monitor, return success.

        ``force_reconnect=True`` bypasses the "already connected" early-out
        so the reconnection loop can re-establish a new client instance.
        """
        if self.connected and not force_reconnect:
            return True

        host = self.config.get("mpd.host", "localhost")
        port = self.config.get("mpd.port", 6600)
        password = self.config.get("mpd.password", None)
        timeout = self.config.get("mpd.timeout", 10)

        result = await self._execute_command("connect", host, port, timeout, password)
        if result:
            self.connected = True
            idle_add_once(self.emit, "connected")

            self.prev_status = {}

            self.stop_monitoring.clear()
            self.monitor_task = asyncio.create_task(self._monitor_status())

            self.stop_reconnecting.set()

            if self._uses_snapcast_for_volume():
                await self.snapcast.connect()

            return True
        else:
            await self._schedule_reconnection()
            return False

    async def _reconnection_loop(self):
        """Retry ``_connect`` every ``reconnect_interval`` seconds until success."""
        idle_add_once(self.emit, "connecting")

        while not self.stop_reconnecting.is_set():
            if not self.connected:
                logging.info("Attempting to reconnect to MPD server...")

                await self._stop_monitoring_task()

                # python-mpd2 doesn't recover a dead client cleanly; build a
                # fresh one before each attempt.
                try:
                    self.client = mpd.asyncio.MPDClient()
                except Exception as e:
                    logging.error("Error creating new MPD client: %s", e)

                if await self._connect(force_reconnect=True):
                    logging.info("Successfully reconnected to MPD server")
                    return
                else:
                    logging.debug("Reconnection attempt failed")

            try:
                await asyncio.wait_for(
                    self.stop_reconnecting.wait(), self.reconnect_interval
                )
            except asyncio.TimeoutError:
                pass

    async def _schedule_reconnection(self):
        """Kick off the reconnection loop, unless one is already running."""
        if self.reconnect_task and not self.reconnect_task.done():
            return

        idle_add_once(self.emit, "connecting-blocked")

        # Tear down any half-open connection first so the fresh client
        # in _reconnection_loop doesn't collide with a stale socket.
        await self._disconnect_internal()

        self.stop_reconnecting.clear()
        self.reconnect_task = asyncio.create_task(self._reconnection_loop())

    def connect_to_server(self):
        """Public entry point: schedule a connection to the configured server."""
        if self.connected:
            return True

        asyncio.create_task(self._schedule_reconnection())

    async def _disconnect_internal(self):
        """Close the MPD socket and cancel the monitor/reconnect tasks."""
        if not self.connected:
            return

        await self._stop_monitoring_task()
        await self._stop_reconnection_task()

        try:
            await self.client.disconnect()  # pyright: ignore[reportGeneralTypeIssues]
        except Exception:
            pass

        self.connected = False

    def disconnect_from_server(self):
        """Public entry point: disconnect from the MPD server."""
        if not self.connected:
            return

        idle_add_once(self.emit, "disconnecting-blocked")

        async def _disconnect_task():
            await self._disconnect_internal()
            idle_add_once(self.emit, "disconnected")

        asyncio.create_task(_disconnect_task())

    def is_connected(self):
        """Return True when the MPD connection is currently open."""
        return self.connected

    # Simple scalar fields that emit ``signal(coerced_value)`` when they
    # change vs. the previous status snapshot. Fields needing composite
    # or multi-arg emission (``repeat`` + ``single``, ``audio``, elapsed's
    # threshold) are handled inline in ``_emit_status_changes``.
    _STATUS_FIELDS = [
        ("volume", "volume-changed", int),
        ("state", "playback-status-changed", str),
        ("random", "random-changed", lambda v: v == "1"),
        ("consume", "consume-changed", lambda v: v == "1"),
        ("bitrate", "bitrate-changed", int),
    ]

    def _emit_status_changes(self, status):
        """Emit GObject signals for MPD status fields that changed."""
        for field, signal, coerce in self._STATUS_FIELDS:
            if field not in status:
                continue
            if status[field] == self.prev_status.get(field):
                continue
            try:
                value = coerce(status[field])
            except (ValueError, TypeError):
                continue
            idle_add_once(self.emit, signal, value)

        # Elapsed: only emit on first appearance or >0.5s change, so the
        # monitor loop's one-second polling doesn't spam handlers.
        if "elapsed" in status:
            try:
                new_elapsed = float(status["elapsed"])
                first_time = "elapsed" not in self.prev_status
                if first_time or abs(new_elapsed - float(self.prev_status.get("elapsed", 0))) > 0.5:
                    idle_add_once(self.emit, "elapsed-changed", new_elapsed)
            except (ValueError, TypeError):
                pass

        # Repeat + single are coupled: MPD has a "single-repeat" mode that
        # only makes sense when both are set, so we emit them together.
        repeat_changed = "repeat" in status and status["repeat"] != self.prev_status.get("repeat")
        single_changed = "single" in status and status["single"] != self.prev_status.get("single")
        if repeat_changed or single_changed:
            repeat = status.get("repeat") == "1"
            single = status.get("single") == "1"
            idle_add_once(self.emit, "repeat-changed", repeat, single)

        # Audio format is "sample_rate:bits:channels" and the signal takes
        # three args (raw string, sample rate, bits).
        if "audio" in status and status["audio"] != self.prev_status.get("audio"):
            try:
                parts = status["audio"].split(":")
                if len(parts) >= 2:
                    sample_rate = int(parts[0])
                    bits = int(parts[1])
                    idle_add_once(
                        self.emit, "audio-changed", status["audio"], sample_rate, bits
                    )
            except (ValueError, TypeError, IndexError):
                pass

        self.prev_status = status.copy()

    async def async_get_albums(self) -> list[Album]:
        """Return every album in the library as a list of :class:`Album`."""
        if not self.connected:
            return []
        result = await self._execute_command("list", "album") or []
        return [Album(title=item["album"]) for item in result if item.get("album")]

    async def async_get_artists(self) -> list[Artist]:
        """Return every artist in the library as a list of :class:`Artist`."""
        if not self.connected:
            return []
        artists_data = await self._execute_command("list", "artist") or []
        return [Artist(name=item["artist"]) for item in artists_data if item.get("artist")]

    async def async_get_songs_by_artist(self, artist: str) -> list[Song]:
        """Return every song whose ``artist`` tag matches."""
        if not self.connected:
            return []
        result = await self._execute_command("find", "artist", artist) or []
        return [Song(**item) for item in result]

    async def async_get_songs_by_album(self, album: str) -> list[Song]:
        """Return every song whose ``album`` tag matches."""
        if not self.connected:
            return []
        result = await self._execute_command("find", "album", album) or []
        return [Song(**item) for item in result]

    async def async_find(self, *filters: str) -> list[Song]:
        """Run MPD's ``find`` with tag/value filter pairs.

        Example: ``await mpd.async_find("artist", "Foo", "album", "Bar")``.
        """
        if not self.connected:
            return []
        result = await self._execute_command("find", *filters) or []
        return [Song(**item) for item in result]

    async def async_get_albums_by_artist(self, artist: str) -> list[Album]:
        """Return every album tagged with ``artist``."""
        if not self.connected:
            return []
        result = await self._execute_command("list", "album", "artist", artist) or []
        return [
            Album(title=item["album"], artist=artist)
            for item in result
            if item.get("album")
        ]

    async def async_get_albums_by_albumartist(self, albumartist: str) -> list[Album]:
        """Return every album whose ``albumartist`` tag matches."""
        if not self.connected:
            return []
        result = (
            await self._execute_command("list", "album", "albumartist", albumartist)
            or []
        )
        return [
            Album(title=item["album"], artist=albumartist)
            for item in result
            if item.get("album")
        ]

    async def async_search(self, type: str, query: str) -> list[Song]:
        """Substring-search the library: ``search(type, query)``."""
        if not self.connected:
            return []
        result = await self._execute_command("search", type, query) or []
        return [Song(**item) for item in result]

    async def async_get_current_playlist(self) -> list[Song]:
        """Return the songs in MPD's active playlist (``playlistinfo``)."""
        if not self.connected:
            return []
        result = await self._execute_command("playlistinfo") or []
        return [Song(**item) for item in result]

    async def async_get_stored_playlists(self):
        """Return MPD's saved playlists (raw dicts from ``listplaylists``)."""
        if not self.connected:
            return []
        return await self._execute_command("listplaylists") or []

    async def async_get_playlist_songs(self, playlist_name: str) -> list[Song]:
        """Return the songs in a stored playlist."""
        if not self.connected:
            return []
        result = await self._execute_command("listplaylistinfo", playlist_name) or []
        return [Song(**item) for item in result]

    async def async_get_album_art(
        self, song_uri: str
    ) -> tuple[bytes | None, str | None, str | None]:
        """Fetch album art for ``song_uri`` via MPD's ``readpicture``.

        Returns ``(binary_data, mime_type, image_path)`` on success or a
        triple of Nones when nothing is cached or embedded. Results are
        memoised through :class:`ImageCache`.
        """
        if not self.connected or not song_uri:
            return None, None, None

        cached_result = self.image_cache.get(song_uri)
        logging.debug(f"ImageCache: Checked cache for {song_uri}, found: {bool(cached_result)}")
        if cached_result:
            return cached_result

        try:
            # readpicture requires MPD 0.22+.
            result = await self._execute_command("readpicture", song_uri)
            if result and "binary" in result:
                binary_data = result["binary"]
                mime_type = result.get("mime", "image/jpeg")
                key = self.image_cache.put(song_uri, binary_data, mime_type)
                return binary_data, mime_type, key
        except Exception as e:
            logging.error("Error getting album art: %s", e)

        return None, None, None

    async def async_get_song_details(self, file_path: str) -> Song | None:
        """Return the :class:`Song` for ``file_path``, or None if not found."""
        if not self.connected or not file_path:
            return None

        try:
            result = await self._execute_command("find", "file", file_path)
            if result and len(result) > 0:
                # find by absolute file path returns a single row.
                return Song(**result[0])
            return None
        except Exception as e:
            logging.error("Error getting song details for %s: %s", file_path, e)
            return None

    async def _stop_monitoring_task(self):
        """Signal the status monitor to stop and await its exit."""
        if self.monitor_task and not self.monitor_task.done():
            self.stop_monitoring.set()
            try:
                await asyncio.wait_for(self.monitor_task, 1)
            except asyncio.TimeoutError:
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
            self.stop_monitoring.clear()
            self.monitor_task = None

    async def _stop_reconnection_task(self):
        """Signal the reconnection loop to stop and await its exit."""
        if self.reconnect_task and not self.reconnect_task.done():
            self.stop_reconnecting.set()
            try:
                await asyncio.wait_for(self.reconnect_task, 1)
            except asyncio.TimeoutError:
                self.reconnect_task.cancel()
                try:
                    await self.reconnect_task
                except asyncio.CancelledError:
                    pass

    async def async_play(self, position: int | None = None):
        """Start playback, optionally jumping to ``position`` in the queue."""
        if position is not None:
            return await self._execute_command("play", position)
        return await self._execute_command("play")

    async def async_pause(self) -> None:
        """Pause playback."""
        await self._execute_command("pause")

    async def async_stop(self) -> None:
        """Stop playback."""
        await self._execute_command("stop")

    async def async_next(self) -> None:
        """Skip to the next track in the queue."""
        await self._execute_command("next")

    async def async_previous(self) -> None:
        """Skip to the previous track in the queue."""
        await self._execute_command("previous")

    async def async_seek(self, position: int) -> None:
        """Seek the current song to ``position`` seconds."""
        await self._execute_command("seekcur", position)

    async def async_delete(self, position: int) -> None:
        """Remove the song at ``position`` from the current playlist."""
        await self._execute_command("delete", position)

    async def async_clear_playlist(self) -> None:
        """Empty the current playlist."""
        await self._execute_command("clear")

    async def async_set_volume(self, volume: int) -> None:
        """Set the volume (0-100), routing to Snapcast when configured."""
        if self._uses_snapcast_for_volume():
            await self.snapcast.set_volume(volume)
        else:
            await self._execute_command("setvol", volume)

    def _uses_snapcast_for_volume(self) -> bool:
        """True when the user has opted into Snapcast-driven volume control."""
        return (
            self.supports_snapcast()
            and self.config.get("volume.method", "mpd").lower() == "snapcast"
        )

    async def async_set_random(self, random: str) -> None:
        """Toggle MPD's random mode; accepts "0"/"1" string for consistency with MPD."""
        if not self.connected:
            return None
        await self._execute_command("random", "1" if random == "1" else "0")

    async def async_set_repeat(self, repeat: str) -> None:
        """Toggle MPD's repeat mode."""
        if not self.connected:
            return None
        await self._execute_command("repeat", "1" if repeat == "1" else "0")

    async def async_set_single(self, single: str) -> None:
        """Toggle MPD's single-song repeat mode."""
        if not self.connected:
            return None
        await self._execute_command("single", "1" if single == "1" else "0")

    async def async_toggle_consume(self) -> None:
        """Flip MPD's consume mode."""
        if not self.connected:
            return None
        consume = int(self.status.get("consume", "0"))
        await self._execute_command("consume", 1 - consume)

    async def async_list_directory(self, directory_path: str = "") -> list[dict]:
        """List directory contents (``lsinfo``); empty string means root."""
        if not self.connected:
            return []

        try:
            return await self._execute_command("lsinfo", directory_path) or []
        except Exception as e:
            logging.error("Error listing directory %s: %s", directory_path, e)
            return []

    async def async_add_songs_to_playlist(self, song_uris: list[str]) -> bool:
        """Append ``song_uris`` to the current playlist; emit playlist-changed."""
        if not self.connected or not song_uris:
            return False

        try:
            for uri in song_uris:
                await self.client.add(  # pyright: ignore[reportAttributeAccessIssue]
                    uri
                )
            idle_add_once(self.emit, "playlist-changed")
            return True
        except Exception as e:
            logging.error("Error adding songs to playlist: %s", e)
            return False

    def supports_snapcast(self) -> bool:
        """True when the python-snapcast library is importable."""
        return HAS_SNAPCAST

    async def _monitor_status(self) -> None:
        """Poll MPD status once per second and emit change signals."""
        last_song_id = None
        last_playlist_version = None
        last_volume_check = 0

        while not self.stop_monitoring.is_set() and self.connected:
            try:
                status = await self._execute_command("status")
                if not status:
                    # Transient fetch failure: back off one tick and retry.
                    try:
                        await asyncio.wait_for(self.stop_monitoring.wait(), 1)
                        continue
                    except asyncio.TimeoutError:
                        continue

                if self._uses_snapcast_for_volume():
                    status["volume"] = str(self.snapcast.volume)

                self.status = status

                # Snapcast exposes per-client volume separately; poll it
                # every 5 seconds so the UI catches external volume changes
                # without hammering the Snapcast server.
                current_time = time.time()
                if (
                    self._uses_snapcast_for_volume()
                    and current_time - last_volume_check > 5
                ):
                    snapcast_volume = await self.snapcast.get_volume()
                    if (
                        snapcast_volume is not None
                        and snapcast_volume != self.snapcast.volume
                    ):
                        self.snapcast.volume = snapcast_volume
                        idle_add_once(self.emit, "volume-changed", snapcast_volume)
                    last_volume_check = current_time
                    status["volume"] = str(self.snapcast.volume)

                self._emit_status_changes(status)

                current_song_id = status.get("songid")
                if current_song_id != last_song_id:
                    last_song_id = current_song_id
                    if current_song_id:
                        song_data = await self._execute_command("currentsong")
                        if song_data:
                            self.current_song = Song(**song_data)
                            bitrate_value = status.get("bitrate", None)
                            self.current_song.bitrate = (
                                f"{bitrate_value} kbps" if bitrate_value else "Unknown"
                            )
                        else:
                            self.current_song = None
                    else:
                        self.current_song = None

                    idle_add_once(self.emit, "song-changed")

                playlist_version = status.get("playlist")
                if playlist_version != last_playlist_version:
                    last_playlist_version = playlist_version
                    idle_add_once(self.emit, "playlist-changed")

                # state-changed fires unconditionally so UI elements that
                # depend on any status field (e.g. the progress bar) refresh.
                idle_add_once(self.emit, "state-changed")

                try:
                    await asyncio.wait_for(self.stop_monitoring.wait(), 1)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logging.error("Monitor error: %s", e)
                if not self.stop_monitoring.is_set():
                    asyncio.create_task(self._schedule_reconnection())
                    idle_add_once(self.emit, "connection-error", "Connection lost")
                break
