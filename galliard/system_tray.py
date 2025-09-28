#!/usr/bin/env python3

# pyright: reportAttributeAccessIssue=false

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402

    APPINDICATOR_AVAILABLE = True
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator  # noqa: E402

        APPINDICATOR_AVAILABLE = True
    except (ValueError, ImportError):
        APPINDICATOR_AVAILABLE = False

from gi.repository import Gtk  # noqa: E402


class SystemTrayIcon:
    """System tray icon for Galliard"""

    def __init__(self, app, config, mpd_client):
        """Initialize system tray icon"""
        self.app = app
        self.config = config
        self.mpd_client = mpd_client
        self.play_pause_item = None
        self.now_playing_item = None

        # Create system tray icon if available
        self.indicator = None
        if APPINDICATOR_AVAILABLE:
            self.create_indicator()

        # Connect signals
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)
        self.mpd_client.connect_signal("state-changed", self.on_state_changed)

    def create_indicator(self):
        """Create app indicator"""
        self.indicator = AppIndicator.Indicator.new(  # type: ignore
            "galliard",
            "audio-x-generic-symbolic",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,  # type: ignore
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)  # type: ignore

        # Create menu
        self.create_menu()

        # Set icon tooltip
        self.update_tooltip("Galliard")

    def create_menu(self):
        """Create tray icon menu"""
        menu = Gtk.Menu()

        # Now playing item (not clickable)
        self.now_playing_item = Gtk.MenuItem(label="Not playing")
        self.now_playing_item.set_sensitive(False)
        menu.append(self.now_playing_item)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Play/Pause item
        self.play_pause_item = Gtk.MenuItem(label="Play")
        self.play_pause_item.connect("activate", self.on_play_pause)
        menu.append(self.play_pause_item)

        # Stop item
        stop_item = Gtk.MenuItem(label="Stop")
        stop_item.connect("activate", self.on_stop)
        menu.append(stop_item)

        # Previous item
        prev_item = Gtk.MenuItem(label="Previous")
        prev_item.connect("activate", self.on_prev)
        menu.append(prev_item)

        # Next item
        next_item = Gtk.MenuItem(label="Next")
        next_item.connect("activate", self.on_next)
        menu.append(next_item)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Show window item
        show_item = Gtk.MenuItem(label="Show Window")
        show_item.connect("activate", self.on_show_window)
        menu.append(show_item)

        # Quit item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit)
        menu.append(quit_item)

        # Show menu
        menu.show_all()

        # Set menu
        if self.indicator:
            self.indicator.set_menu(menu)

    def update_tooltip(self, text):
        """Update tray icon tooltip"""
        if APPINDICATOR_AVAILABLE and self.indicator and self.now_playing_item:
            # AppIndicator doesn't support tooltips directly
            # We can use the title/label of the first menu item as a workaround
            self.now_playing_item.set_label(text)

    def on_song_changed(self, client):
        """Handle song change"""
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            self.update_tooltip("Galliard")
            return

        # Get song information
        song = self.mpd_client.current_song
        title = song.get("title", song.get("file", "Unknown"))
        artist = song.get("artist", "Unknown")

        # Update tooltip
        self.update_tooltip(f"{title} - {artist}")

    def on_state_changed(self, client):
        """Handle playback state change"""
        if not self.mpd_client.is_connected() or not self.play_pause_item:
            return

        status = self.mpd_client.status
        state = status.get("state", "stop")

        if state == "play" and self.play_pause_item:
            self.play_pause_item.set_label("Pause")
        elif self.play_pause_item:
            self.play_pause_item.set_label("Play")

    def on_play_pause(self, widget):
        """Handle play/pause menu item"""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        if status.get("state") == "play":
            self.mpd_client.pause()
        else:
            self.mpd_client.play()

    def on_stop(self, widget):
        """Handle stop menu item"""
        if self.mpd_client.is_connected():
            self.mpd_client.stop()

    def on_prev(self, widget):
        """Handle previous menu item"""
        if self.mpd_client.is_connected():
            self.mpd_client.previous()

    def on_next(self, widget):
        """Handle next menu item"""
        if self.mpd_client.is_connected():
            self.mpd_client.next()

    def on_show_window(self, widget):
        """Handle show window menu item"""
        window = self.app.props.active_window
        if window:
            window.present()

    def on_quit(self, widget):
        """Handle quit menu item"""
        self.app.quit()

    def cleanup(self):
        """Clean up system tray icon"""
        # Nothing to clean up with AppIndicator
        pass
