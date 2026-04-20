#!/usr/bin/env python3

import logging

import gi

from gi.repository import GObject

try:
    gi.require_version("GnomeDesktop", "4.0")
    from gi.repository import GnomeDesktop  # type: ignore  noqa: E402

    MEDIA_KEYS_AVAILABLE = True
except (ValueError, ImportError):
    MEDIA_KEYS_AVAILABLE = False


class MediaKeysManager(GObject.Object):
    """Bridge GNOME's media-key grabs to MPD transport commands."""

    def __init__(self, app, mpd_client):
        """Grab media-player keys if the GNOME proxy is available."""
        GObject.Object.__init__(self)

        self.app = app
        self.mpd_client = mpd_client
        self.media_keys = None

        if MEDIA_KEYS_AVAILABLE:
            self.setup_media_keys()

    def setup_media_keys(self):
        """Open the GNOME media-keys proxy and grab the player keys."""
        try:
            self.media_keys = GnomeDesktop.MediaKeysProxy.new()  # type: ignore
            self.media_keys.grab_media_player_keys("GnomeMPDConn", 0)

            self.media_keys.connect(
                "media-player-key-pressed", self.on_media_key_pressed
            )
        except Exception as e:
            logging.error("Failed to set up media keys: %s", e)

    def on_media_key_pressed(self, proxy, application, key):
        """Route a media-key press to the equivalent MPD command."""
        if not self.mpd_client.is_connected():
            return

        if key == "Play":
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
        """Release the media-player key grab on shutdown."""
        if MEDIA_KEYS_AVAILABLE and self.media_keys:
            self.media_keys.release_media_player_keys("GnomeMPDConn")
