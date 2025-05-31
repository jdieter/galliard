#!/usr/bin/env python3

import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify  # noqa: E402


class NotificationManager:
    """Notification manager for Galliard"""

    def __init__(self, app, config, mpd_client):
        """Initialize notification manager"""
        self.app = app
        self.config = config
        self.mpd_client = mpd_client

        # Initialize notifications
        Notify.init("Galliard")

        # Create a notification
        self.notification = Notify.Notification.new(
            "Galliard", "Connected to MPD server", "audio-x-generic"
        )

        # Connect signals
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)

    def on_song_changed(self, client):
        """Handle song change"""
        # Check if notifications are enabled
        if not self.config.get("ui.show_notifications", True):
            return

        # Check if we have a current song
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            return

        # Get song information
        song = self.mpd_client.current_song
        title = song.get("title", song.get("file", "Unknown"))
        artist = song.get("artist", "Unknown")
        album = song.get("album", "Unknown")

        # Update notification
        self.notification.update(title, f"{artist}\n{album}", "audio-x-generic")

        # Show notification
        self.notification.show()

    def cleanup(self):
        """Clean up notifications"""
        Notify.uninit()
