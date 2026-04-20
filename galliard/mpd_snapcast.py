"""Snapcast integration composed onto :class:`MPDConn` as ``mpd.snapcast``.

The controller owns the server/client handles and exposes volume control
plus a client-list query used by the preferences page.
"""

import logging

from galliard.utils.glib import idle_add_once

try:
    import snapcast.control
except ImportError:
    logging.warning("Warning: python-snapcast library not found.")
    logging.warning("Please install it with: pip install python-snapcast")
    HAS_SNAPCAST = False
else:
    HAS_SNAPCAST = True

# Snapcast's JSON-RPC control channel listens here by default. (1780 is
# the HTTP/websocket variant, which python-snapcast doesn't speak.)
DEFAULT_CONTROL_PORT = 1705


class SnapcastController:
    """Snapcast state + operations, owned by a parent :class:`MPDConn`.

    The controller borrows ``mpd_conn.config``, ``.loop``, and ``.emit``
    rather than importing ``MPDConn`` to keep the dependency one-directional.
    """

    def __init__(self, mpd_conn):
        """Initialise empty state; ``connect`` is called lazily."""
        self._mpd = mpd_conn
        self.server = None
        self.client = None
        self.volume = 0
        self.clients: list[dict] = []

    @property
    def available(self) -> bool:
        """True if the python-snapcast library is importable."""
        return HAS_SNAPCAST

    def _extract_clients(self, server) -> list[dict]:
        """Flatten a Snapcast server's clients into plain dicts for the UI."""
        return [
            {
                "id": client.identifier,
                "name": client.friendly_name or client.identifier,
                "connected": client.connected,
                "volume": client.volume,
            }
            for client in server.clients
        ]

    async def connect(self) -> bool:
        """Connect to the configured Snapcast server and select a client."""
        if not HAS_SNAPCAST:
            logging.warning(
                "Cannot connect to Snapcast: python-snapcast library not installed"
            )
            return False

        host = self._mpd.config.get("snapcast.host", "localhost")
        port = self._mpd.config.get("snapcast.port", DEFAULT_CONTROL_PORT)

        try:
            self.server = await snapcast.control.create_server(  # type: ignore
                self._mpd.loop, host, port
            )
            self.clients = self._extract_clients(self.server)
            await self.select_client()
            logging.debug("Connected to Snapcast server at %s:%s", host, port)
            return True
        except Exception as e:
            logging.error("Error connecting to Snapcast server: %s", e)
            return False

    async def select_client(self) -> None:
        """Pick the Snapcast client to control based on ``snapcast.client_id``.

        If no client is configured, or the configured one is missing, fall
        back to the first available client and persist the choice.
        """
        if not self.server:
            return

        client_id = self._mpd.config.get("snapcast.client_id", "")
        if not client_id and self.server.clients:
            self.client = self.server.clients[0]
            self._mpd.config.set("snapcast.client_id", self.client.identifier)
            logging.info(
                "No Snapcast client selected, using %s",
                self.client.friendly_name,
            )
            return

        for client in self.server.clients:
            if client.identifier == client_id:
                self.client = client
                self.volume = client.volume
                logging.debug("Selected Snapcast client: %s", client.friendly_name)
                return

        logging.warning("Selected Snapcast client '%s' not found", client_id)
        if self.server.clients:
            self.client = self.server.clients[0]
            self._mpd.config.set("snapcast.client_id", self.client.identifier)

    async def set_volume(self, volume: int) -> bool:
        """Set the selected client's volume."""
        if not HAS_SNAPCAST:
            logging.error("Cannot set Snapcast volume: python-snapcast library not installed")
            return False

        if not self.client:
            if not self.server:
                await self.connect()
            if not self.client:
                logging.warning("No Snapcast client selected")
                return False

        try:
            await self.client.set_volume(volume)
            self.volume = volume
            idle_add_once(self._mpd.emit, "volume-changed", volume)
            return True
        except Exception as e:
            logging.error("Error setting Snapcast volume: %s", e)
            await self.connect()
            return False

    async def get_volume(self) -> int | None:
        """Return the selected client's current volume, or None."""
        if not HAS_SNAPCAST:
            logging.error("Cannot get Snapcast volume: python-snapcast library not installed")
            return None

        if not self.client:
            if not self.server:
                await self.connect()
            if not self.client:
                logging.warning("No Snapcast client selected")
                return None

        try:
            self.volume = self.client.volume
            return self.volume
        except Exception as e:
            logging.error("Error getting Snapcast volume: %s", e)
            await self.connect()
            return None

    async def get_clients(self, host: str | None = None, port: int | None = None) -> bool:
        """Refresh ``self.clients`` from a possibly-ephemeral server connection.

        The preferences page calls this to list available clients, even
        before there's a persistent server connection.
        """
        if not HAS_SNAPCAST:
            logging.error("Cannot get Snapcast clients: python-snapcast library not installed")
            return False

        if host is None:
            host = self._mpd.config.get("snapcast.host", "localhost")
        if port is None:
            port = int(self._mpd.config.get("snapcast.port", DEFAULT_CONTROL_PORT))

        try:
            server = await snapcast.control.create_server(  # type: ignore
                self._mpd.loop, host, port
            )
            self.clients = self._extract_clients(server)
            # If we opened a temporary connection, close it back down.
            if server != self.server:
                server.stop()
            return True
        except Exception as e:
            logging.error("Error getting Snapcast clients: %s", e)
            return False
