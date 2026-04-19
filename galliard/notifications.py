#!/usr/bin/env python3

import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify  # noqa: E402


class NotificationManager:
    """Shows a libnotify desktop notification on every MPD song change."""

    def __init__(self, app, config, mpd_client):
        """Initialise libnotify and subscribe to the song-changed signal."""
        self.app = app
        self.config = config
        self.mpd_client = mpd_client

        Notify.init("Galliard")

        self.notification = Notify.Notification.new(
            "Galliard", "Connected to MPD server", "audio-x-generic"
        )

        self.mpd_client.connect_signal("song-changed", self.on_song_changed)

    def on_song_changed(self, client):
        """Raise a notification with the new song's title/artist/album."""
        if not self.config.get("ui.show_notifications", True):
            return

        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            return

        song = self.mpd_client.current_song
        title = song.get("title", song.get("file", "Unknown"))
        artist = song.get("artist", "Unknown")
        album = song.get("album", "Unknown")

        self.notification.update(title, f"{artist}\n{album}", "audio-x-generic")
        self.notification.show()

    def cleanup(self):
        """Uninitialise libnotify."""
        Notify.uninit()
