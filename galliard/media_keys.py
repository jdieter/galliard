#!/usr/bin/env python3

import gi

from gi.repository import GObject

try:
    gi.require_version("GnomeDesktop", "4.0")
    from gi.repository import GnomeDesktop  # noqa: E402

    MEDIA_KEYS_AVAILABLE = True
except (ValueError, ImportError):
    MEDIA_KEYS_AVAILABLE = False


class MediaKeysManager(GObject.Object):
    """Media keys manager for Galliard"""

    def __init__(self, app, mpd_client):
        """Initialize media keys manager"""
        GObject.Object.__init__(self)

        self.app = app
        self.mpd_client = mpd_client

        # Media keys proxy
        self.media_keys = None

        # Try to set up media keys
        if MEDIA_KEYS_AVAILABLE:
            self.setup_media_keys()

    def setup_media_keys(self):
        """Set up media keys"""
        try:
            # Initialize media keys
            self.media_keys = GnomeDesktop.MediaKeysProxy.new()
            self.media_keys.grab_media_player_keys("GnomeMPDConn", 0)

            # Connect signal
            self.media_keys.connect(
                "media-player-key-pressed", self.on_media_key_pressed
            )
        except Exception as e:
            print(f"Failed to set up media keys: {e}")

    def on_media_key_pressed(self, proxy, application, key):
        """Handle media key press"""
        if not self.mpd_client.is_connected():
            return

        if key == "Play":
            # Toggle play/pause
            status = self.mpd_client.status
            if status.get("state") == "play":
                self.mpd_client.pause()
            else:
                self.mpd_client.play()
        elif key == "Stop":
            self.mpd_client.stop()
        elif key == "Next":
            self.mpd_client.next()
        elif key == "Previous":
            self.mpd_client.previous()

    def release(self):
        """Release media keys"""
        if MEDIA_KEYS_AVAILABLE and self.media_keys:
            self.media_keys.release_media_player_keys("GnomeMPDConn")
