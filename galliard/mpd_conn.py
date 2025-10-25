#!/usr/bin/env python3

import time
import socket
import asyncio
from typing import Any

from gi.repository import GLib, GObject
from gi.events import GLibEventLoopPolicy
from galliard.models import Song, Album, Artist

try:
    import mpd.asyncio
except ImportError:
    print("Error: python-mpd2 library with asyncio not found.")
    print("Please install it with: pip install python-mpd2")
    exit(1)

try:
    import snapcast.control
except ImportError:
    print("Warning: python-snapcast library not found.")
    print("Please install it with: pip install python-snapcast")
    HAS_SNAPCAST = False
else:
    HAS_SNAPCAST = True


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
        """Initialize the MPD client wrapper"""
        super().__init__()
        self.config = config
        self.client = mpd.asyncio.MPDClient()
        self.connected = False
        self.current_song = None
        self.status = {}

        # Store previous status values for comparison
        self.prev_status = {}

        # Event loop - get the existing one or create new one
        policy = GLibEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        self.loop = policy.get_event_loop()

        # Status monitoring task
        self.monitor_task = None
        self.stop_monitoring = asyncio.Event()

        # Reconnection handling
        self.reconnect_task = None
        self.stop_reconnecting = asyncio.Event()
        self.reconnect_interval = 5  # seconds between reconnection attempts
        self.auto_reconnect = True

        # Command lock to prevent concurrent MPD commands
        self.cmd_lock = asyncio.Lock()

        # Add Snapcast related properties
        self.snapcast_client = None
        self.snapcast_server = None
        self.snapcast_client_id = self.config.get("snapcast.client_id", "")
        self.snapcast_volume = 0
        self.snapcast_clients = []

    async def _execute_command(self, cmd, *args, **kwargs) -> Any:
        """Execute MPD command with async lock to prevent concurrent access"""
        if not self.connected and cmd != "connect":
            return None

        async with self.cmd_lock:
            try:
                if cmd == "connect":
                    # Special handling for connect
                    host, port, timeout, password = args
                    await self.client.connect(host, port, timeout)
                    if password:
                        await self.client.password(password)  # type: ignore
                    return True
                else:
                    # Execute any other MPD command
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
                print("MPD error:", e)

                # Schedule reconnection if needed
                asyncio.create_task(self._schedule_reconnection())

                # Emit error signal via GLib main context
                if "Connection" in str(e):
                    GLib.idle_add(self.emit, "connection-error", "Connection lost")
                else:
                    GLib.idle_add(self.emit, "connection-error", str(e))
                return None
            except Exception as e:
                print(f"Unexpected error executing {cmd}: {e}")
                return None

    def connect_signal(self, signal_name, callback_func, *user_data):
        """Connect a callback function to a signal

        Args:
            signal_name (str): Name of the signal to connect to (e.g., 'connected', 'song-changed')
            callback_func (callable): Function to call when signal is emitted
            *user_data: Optional additional data to pass to the callback function

        Returns:
            int: Signal handler ID that can be used to disconnect the signal

        Raises:
            ValueError: If signal_name is not a valid signal
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

        # Connect the signal and return the handler ID
        handler_id = super().connect(signal_name, callback_func, *user_data)
        return handler_id

    def disconnect_signal(self, handler_id):
        """Disconnect a previously connected signal handler

        Args:
            handler_id (int): Signal handler ID returned from connect_signal
        """
        if handler_id:
            super().disconnect(handler_id)

    async def _connect(self, force_reconnect=False):
        """Connect to MPD server asynchronously

        Args:
            force_reconnect (bool): Force reconnection even if already connected

        Returns:
            bool: True if connection successful, False otherwise
        """
        if self.connected and not force_reconnect:
            return True

        host = self.config.get("mpd.host", "localhost")
        port = self.config.get("mpd.port", 6600)
        password = self.config.get("mpd.password", None)
        timeout = self.config.get("mpd.timeout", 10)

        # Execute connect command
        result = await self._execute_command("connect", host, port, timeout, password)
        if result:
            self.connected = True
            GLib.idle_add(self.emit, "connected")

            # Reset previous status
            self.prev_status = {}

            # Start monitoring task
            self.stop_monitoring.clear()
            self.monitor_task = asyncio.create_task(self._monitor_status())

            # Clear reconnection flag if we were in a reconnection state
            self.stop_reconnecting.set()

            # Start snapcast connection if needed
            if self.config.get("volume.method", "mpd").lower() == "snapcast":
                await self._connect_snapcast()

            return True
        else:
            # Start reconnection task
            await self._schedule_reconnection()
            return False

    async def _reconnection_loop(self):
        """Asynchronous loop that attempts to reconnect to MPD server"""
        GLib.idle_add(self.emit, "connecting")

        while not self.stop_reconnecting.is_set():
            if not self.connected:
                print("Attempting to reconnect to MPD server...")

                # Stop monitoring task if running
                await self._stop_monitoring_task()

                # Try to create a new client instance
                try:
                    self.client = mpd.asyncio.MPDClient()
                except Exception as e:
                    print(f"Error creating new MPD client: {e}")

                # Attempt reconnection using our regular connect method
                # But bypass the normal "already connected" check
                if await self._connect(force_reconnect=True):
                    print("Successfully reconnected to MPD server")
                    return  # Exit reconnection task on successful reconnection
                else:
                    print("Reconnection attempt failed")

            # Wait before trying again
            try:
                await asyncio.wait_for(
                    self.stop_reconnecting.wait(), self.reconnect_interval
                )
            except asyncio.TimeoutError:
                pass  # Just continue the loop

    async def _schedule_reconnection(self):
        """Start a task to handle reconnection"""
        if self.reconnect_task and not self.reconnect_task.done():
            return  # Reconnection task already running

        GLib.idle_add(self.emit, "connecting-blocked")

        # Ensure we clean up any existing connection
        await self._disconnect_internal()

        # Start reconnection task
        self.stop_reconnecting.clear()
        self.reconnect_task = asyncio.create_task(self._reconnection_loop())

    def connect_to_server(self):
        """Connect to MPD server - API method that creates a connect task"""
        if self.connected:
            return True

        asyncio.create_task(self._schedule_reconnection())

    async def _disconnect_internal(self):
        """Internal disconnect method"""
        if not self.connected:
            return

        # Stop monitoring task if running
        await self._stop_monitoring_task()

        # Stop reconnection task if running
        await self._stop_reconnection_task()

        try:
            await self.client.disconnect()  # pyright: ignore[reportGeneralTypeIssues]
        except Exception:
            pass

        self.connected = False

    def disconnect_from_server(self):
        """Disconnect from MPD server - API method"""
        if not self.connected:
            return

        GLib.idle_add(self.emit, "disconnecting-blocked")

        async def _disconnect_task():
            await self._disconnect_internal()
            GLib.idle_add(self.emit, "disconnected")

        asyncio.create_task(_disconnect_task())

    def is_connected(self):
        """Check if connected to MPD server"""
        return self.connected

    def _emit_status_changes(self, status):
        """Emit signals for changed status values"""
        # Check volume changes
        if "volume" in status and (
            "volume" not in self.prev_status
            or status["volume"] != self.prev_status["volume"]
        ):
            try:
                volume = int(status["volume"])
                GLib.idle_add(self.emit, "volume-changed", volume)
            except (ValueError, TypeError):
                pass

        # Check playback state changes
        if "state" in status and (
            "state" not in self.prev_status
            or status["state"] != self.prev_status["state"]
        ):
            GLib.idle_add(self.emit, "playback-status-changed", status["state"])

        # Check elapsed time changes
        if "elapsed" in status and (
            "elapsed" not in self.prev_status
            or abs(float(status["elapsed"]) - float(self.prev_status.get("elapsed", 0)))
            > 0.5
        ):
            try:
                elapsed = float(status["elapsed"])
                GLib.idle_add(self.emit, "elapsed-changed", elapsed)
            except (ValueError, TypeError):
                pass

        # Check repeat mode changes
        if (
            "repeat" in status
            and (
                "repeat" not in self.prev_status
                or status["repeat"] != self.prev_status["repeat"]
            )
        ) or (
            "single" in status
            and (
                "single" not in self.prev_status
                or status["single"] != self.prev_status["single"]
            )
        ):
            repeat = status["repeat"] == "1"
            single = status["single"] == "1"
            GLib.idle_add(self.emit, "repeat-changed", repeat, single)

        # Check random mode changes
        if "random" in status and (
            "random" not in self.prev_status
            or status["random"] != self.prev_status["random"]
        ):
            random = status["random"] == "1"
            GLib.idle_add(self.emit, "random-changed", random)

        # Check consume mode changes
        if "consume" in status and (
            "consume" not in self.prev_status
            or status["consume"] != self.prev_status["consume"]
        ):
            consume = status["consume"] == "1"
            GLib.idle_add(self.emit, "consume-changed", consume)

        # Check audio format changes
        if "audio" in status and (
            "audio" not in self.prev_status
            or status["audio"] != self.prev_status["audio"]
        ):
            try:
                # Audio format is sample_rate:bits:channels
                parts = status["audio"].split(":")
                if len(parts) >= 2:
                    sample_rate = int(parts[0])
                    bits = int(parts[1])
                    # channels = int(parts[2]) if len(parts) > 2 else 2
                    GLib.idle_add(
                        self.emit, "audio-changed", status["audio"], sample_rate, bits
                    )
            except (ValueError, TypeError, IndexError):
                pass

        # Check bitrate changes
        if "bitrate" in status and (
            "bitrate" not in self.prev_status
            or status["bitrate"] != self.prev_status["bitrate"]
        ):
            try:
                bitrate = int(status["bitrate"])
                GLib.idle_add(self.emit, "bitrate-changed", bitrate)
            except (ValueError, TypeError):
                pass

        # Update previous status
        self.prev_status = status.copy()

    async def async_get_albums(self) -> list[Album]:
        """Get all albums asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("list", "album") or []
        return [Album(**item) for item in result]

    async def async_get_artists(self) -> list[Artist]:
        """Get all artists asynchronously"""
        if not self.connected:
            return []
        artists_data = await self._execute_command("list", "artist") or []
        return [Artist(**item) for item in artists_data]

    async def async_get_songs_by_artist(self, artist: str) -> list[Song]:
        """Get songs by artist asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("find", "artist", artist) or []
        return [Song(**item) for item in result]

    async def async_get_songs_by_album(self, album: str) -> list[Song]:
        """Get songs by album asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("find", "album", album) or []
        return [Song(**item) for item in result]

    async def async_get_albums_by_artist(self, artist: str) -> list[Album]:
        """Get albums by artist asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("list", "album", "artist", artist) or []
        return [Album(**item) for item in result]

    async def async_search(self, query: str) -> list[Song]:
        """Search for songs asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("search", "any", query) or []
        return [Song(**item) for item in result]

    async def async_get_current_playlist(self) -> list[Song]:
        """Get current playlist asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("playlistinfo") or []
        return [Song(**item) for item in result]

    async def async_get_stored_playlists(self):
        """Get stored playlists asynchronously"""
        if not self.connected:
            return []
        return await self._execute_command("listplaylists") or []

    async def async_get_playlist_songs(self, playlist_name: str) -> list[Song]:
        """Get songs in stored playlist asynchronously"""
        if not self.connected:
            return []
        result = await self._execute_command("listplaylistinfo", playlist_name) or []
        return [Song(**item) for item in result]

    async def async_get_album_art(
        self, song_uri: str
    ) -> tuple[bytes | None, str | None]:
        """Get album art for a song

        Args:
            song_uri (str): URI of the song to get album art for

        Returns:
            tuple: (binary_data, mime_type) if album art exists, (None, None) otherwise

        The binary_data can be loaded into a GdkPixbuf using:
        ```
        loader = GdkPixbuf.PixbufLoader()
        loader.write(binary_data)
        loader.close()
        pixbuf = loader.get_pixbuf()
        ```
        """
        if not self.connected or not song_uri:
            return None, None

        try:
            # MPD 0.22+ supports readpicture command
            result = await self._execute_command("readpicture", song_uri)
            if result and "binary" in result:
                return result["binary"], result.get("mime", "image/jpeg")
        except Exception as e:
            print(f"Error getting album art: {e}")

        return None, None

    async def async_get_song_details(self, file_path: str) -> Song | None:
        """Get detailed information about a song

        Args:
            file_path (str): Path to the song file in the MPD library

        Returns:
            dict: Song metadata dictionary or None if not found/error
        """
        if not self.connected or not file_path:
            return None

        try:
            # Use find command with file filter to get full song details
            result = await self._execute_command("find", "file", file_path)
            if result and len(result) > 0:
                return Song(**result[0])  # Return the first (and should be only) match
            return None
        except Exception as e:
            print(f"Error getting song details for {file_path}: {e}")
            return None

    async def _stop_monitoring_task(self):
        """Stop the monitoring task if it's running"""
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
        """Stop the reconnection task if it's running"""
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

    # New async methods for player control

    async def async_play(self, position: int | None = None):
        """Start playback at optional position asynchronously"""
        if position is not None:
            return await self._execute_command("play", position)
        return await self._execute_command("play")

    async def async_pause(self) -> None:
        """Pause playback asynchronously"""
        await self._execute_command("pause")

    async def async_stop(self) -> None:
        """Stop playback asynchronously"""
        await self._execute_command("stop")

    async def async_next(self) -> None:
        """Play next track asynchronously"""
        await self._execute_command("next")

    async def async_previous(self) -> None:
        """Play previous track asynchronously"""
        await self._execute_command("previous")

    async def async_seek(self, position: int) -> None:
        """Seek to position in seconds asynchronously"""
        await self._execute_command("seekcur", position)

    async def async_delete(self, position: int) -> None:
        """Delete song at position from current playlist asynchronously"""
        await self._execute_command("delete", position)

    async def async_clear_playlist(self) -> None:
        """Clear the current playlist asynchronously"""
        await self._execute_command("clear")

    async def async_set_volume(self, volume: int) -> None:
        """Set volume (0-100) asynchronously"""
        # Check if we're using Snapcast for volume control
        if self.config.get("volume.method", "mpd").lower() == "snapcast":
            await self._async_set_snapcast_volume(volume)
        else:
            await self._execute_command("setvol", volume)

    async def async_set_random(self, random: str) -> None:
        """Set random playback asynchronously"""
        if not self.connected:
            return None
        await self._execute_command("random", "1" if random == "1" else "0")

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode asynchronously"""
        if not self.connected:
            return None
        await self._execute_command("repeat", "1" if repeat == "1" else "0")

    async def async_set_single(self, single: str) -> None:
        """Set single mode asynchronously"""
        if not self.connected:
            return None
        await self._execute_command("single", "1" if single == "1" else "0")

    async def async_toggle_consume(self) -> None:
        """Toggle consume mode asynchronously"""
        if not self.connected:
            return None
        consume = int(self.status.get("consume", "0"))
        await self._execute_command("consume", 1 - consume)

    async def async_list_directory(self, directory_path: str = "") -> list[dict]:
        """List contents of a directory in the MPD music library asynchronously

        Args:
            directory_path (str): Path to list, empty string for root directory

        Returns:
            list: Directory contents with metadata, or empty list on error/empty directory
        """
        if not self.connected:
            return []

        try:
            return await self._execute_command("lsinfo", directory_path) or []
        except Exception as e:
            print(f"Error listing directory {directory_path}: {e}")
            return []

    async def async_add_songs_to_playlist(self, song_uris: list[str]) -> bool:
        """Add multiple songs to the current playlist using batch commands

        Args:
            song_uris (list): List of song URIs to add to the playlist

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connected or not song_uris:
            return False

        try:
            # Add each song to the command list
            for uri in song_uris:
                await self.client.add(  # pyright: ignore[reportAttributeAccessIssue]
                    uri
                )
            # Emit playlist-changed signal
            GLib.idle_add(self.emit, "playlist-changed")
            return True
        except Exception as e:
            print(f"Error adding songs to playlist: {e}")
            return False

    async def _connect_snapcast(self) -> bool:
        """Connect to Snapcast server asynchronously"""
        if not HAS_SNAPCAST:
            print("Cannot connect to Snapcast: python-snapcast library not installed")
            return False

        host = self.config.get("snapcast.host", "localhost")
        port = self.config.get("snapcast.port", 1780)

        try:
            # Create a new Snapcast server connection
            server = await snapcast.control.create_server(  # type: ignore
                self.loop, host, port
            )
            self.snapcast_server = server

            # Get available clients
            self.snapcast_clients = [
                {
                    "id": client.identifier,
                    "name": client.friendly_name or client.identifier,
                    "connected": client.connected,
                    "volume": client.volume,
                }
                for client in server.clients
            ]

            # Select client to control
            await self._select_snapcast_client()

            print(f"Connected to Snapcast server at {host}:{port}")
            return True
        except Exception as e:
            print(f"Error connecting to Snapcast server: {e}")
            return False

    async def _select_snapcast_client(self) -> None:
        """Select the Snapcast client to control based on config"""
        if not self.snapcast_server:
            return

        client_id = self.config.get("snapcast.client_id", "")
        if not client_id and self.snapcast_server.clients:
            # If no client is selected, use the first available one
            self.snapcast_client = self.snapcast_server.clients[0]
            self.config.set("snapcast.client_id", self.snapcast_client.identifier)
            print(
                f"No Snapcast client selected, using {self.snapcast_client.friendly_name}"
            )
        else:
            # Find the selected client
            for client in self.snapcast_server.clients:
                if client.identifier == client_id:
                    self.snapcast_client = client
                    self.snapcast_volume = client.volume
                    print(f"Selected Snapcast client: {client.friendly_name}")
                    break
            else:
                print(f"Selected Snapcast client '{client_id}' not found")
                if self.snapcast_server.clients:
                    self.snapcast_client = self.snapcast_server.clients[0]
                    self.config.set(
                        "snapcast.client_id", self.snapcast_client.identifier
                    )

    async def _async_set_snapcast_volume(self, volume: int) -> bool:
        """Set volume using Snapcast API"""
        if not HAS_SNAPCAST:
            print("Cannot set Snapcast volume: python-snapcast library not installed")
            return False

        if not self.snapcast_client:
            # Try to connect to Snapcast if not already connected
            if not self.snapcast_server:
                await self._connect_snapcast()

            if not self.snapcast_client:
                print("No Snapcast client selected")
                return False

        try:
            # Set volume
            await self.snapcast_client.set_volume(volume)
            self.snapcast_volume = volume
            # Emit volume change signal
            GLib.idle_add(self.emit, "volume-changed", volume)
            return True
        except Exception as e:
            print(f"Error setting Snapcast volume: {e}")
            # Try to reconnect
            await self._connect_snapcast()
            return False

    async def async_get_snapcast_clients(
        self, host: str | None = None, port: int | None = None
    ) -> bool:
        """Get list of Snapcast clients asynchronously

        Args:
            callback (callable): Function to call with client list
            host (str): Snapcast server host
            port (int): Snapcast server port
        """
        if not HAS_SNAPCAST:
            print("Cannot get Snapcast clients: python-snapcast library not installed")
            return False

        if host is None:
            host = self.config.get("snapcast.host", "localhost")
        if port is None:
            port = int(self.config.get("snapcast.port", 1780))

        try:
            # Create a new Snapcast server connection
            server = await snapcast.control.create_server(  # type: ignore
                self.loop, host, port
            )

            # Extract client information
            clients = [
                {
                    "id": client.identifier,
                    "name": client.friendly_name or client.identifier,
                    "connected": client.connected,
                    "volume": client.volume,
                }
                for client in server.clients
            ]
            print(clients)

            # Store clients for later use
            self.snapcast_clients = clients

            # Clean up temporary connection
            if server != self.snapcast_server:
                server.stop()

            return True

        except Exception as e:
            print(f"Error getting Snapcast clients: {e}")
            return False

    async def async_get_snapcast_volume(self) -> int | None:
        """Get current volume from Snapcast"""
        if not HAS_SNAPCAST:
            print("Cannot get Snapcast volume: python-snapcast library not installed")
            return None

        if not self.snapcast_client:
            # Try to connect to Snapcast if not already connected
            if not self.snapcast_server:
                await self._connect_snapcast()

            if not self.snapcast_client:
                print("No Snapcast client selected")
                return None

        try:
            # Refresh client information
            self.snapcast_volume = self.snapcast_client.volume
            return self.snapcast_volume
        except Exception as e:
            print(f"Error getting Snapcast volume: {e}")
            # Try to reconnect
            await self._connect_snapcast()
            return None

    async def _monitor_status(self) -> None:
        """Monitor MPD status changes asynchronously"""
        last_song_id = None
        last_playlist_version = None
        last_volume_check = 0

        while not self.stop_monitoring.is_set() and self.connected:
            print("checking MPD status...")
            try:
                # Get status using async command
                status = await self._execute_command("status")
                if not status:
                    # If status fetch failed, wait a bit and retry
                    try:
                        await asyncio.wait_for(self.stop_monitoring.wait(), 1)
                        continue
                    except asyncio.TimeoutError:
                        continue  # Continue the loop after timeout

                self.status = status

                # If using Snapcast for volume, periodically check its volume
                current_time = time.time()
                if (
                    self.config.get("volume.method", "mpd").lower() == "snapcast"
                    and current_time - last_volume_check > 5
                ):  # Check every 5 seconds
                    snapcast_volume = await self.async_get_snapcast_volume()
                    if (
                        snapcast_volume is not None
                        and snapcast_volume != self.snapcast_volume
                    ):
                        self.snapcast_volume = snapcast_volume
                        GLib.idle_add(self.emit, "volume-changed", snapcast_volume)
                    last_volume_check = current_time

                    # Update the volume in status for compatibility
                    status["volume"] = str(self.snapcast_volume)

                # Emit granular status change signals
                self._emit_status_changes(status)

                # Check if song changed
                current_song_id = status.get("songid")
                if current_song_id != last_song_id:
                    last_song_id = current_song_id
                    if current_song_id:
                        self.current_song = await self._execute_command("currentsong")
                        if self.current_song:
                            # Add bitrate to current song data
                            bitrate_value = status.get("bitrate", None)
                            self.current_song["bitrate"] = (
                                f"{bitrate_value} kbps" if bitrate_value else "Unknown"
                            )
                    else:
                        self.current_song = None

                    GLib.idle_add(self.emit, "song-changed")

                # Check if playlist changed
                playlist_version = status.get("playlist")
                if playlist_version != last_playlist_version:
                    last_playlist_version = playlist_version
                    GLib.idle_add(self.emit, "playlist-changed")

                # Always emit state changed for updating UI
                GLib.idle_add(self.emit, "state-changed")

                # Sleep for a short time before polling again
                try:
                    await asyncio.wait_for(self.stop_monitoring.wait(), 1)
                except asyncio.TimeoutError:
                    pass  # Just continue the loop

            except Exception as e:
                print(f"Monitor error: {e}")
                if not self.stop_monitoring.is_set():
                    asyncio.create_task(self._schedule_reconnection())
                    GLib.idle_add(self.emit, "connection-error", "Connection lost")
                break
