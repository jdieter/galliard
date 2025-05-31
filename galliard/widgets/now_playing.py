#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from galliard.utils.album_art import load_album_art  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402


class NowPlayingView(Gtk.Box):
    """Now Playing view widget for Galliard"""

    def __init__(self, mpd_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.mpd_client = mpd_client

        # Create UI
        self.create_ui()

        # Connect signals
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)
        self.mpd_client.connect_signal("state-changed", self.on_state_changed)

        # Connect additional signals for granular updates (removed elapsed-changed)
        self.mpd_client.connect_signal(
            "playback-status-changed", self.on_playback_status_changed
        )
        self.mpd_client.connect_signal("bitrate-changed", self.on_bitrate_changed)

    def create_ui(self):
        """Create the user interface"""
        # Main layout box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_vexpand(True)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_spacing(12)

        # Top section with album art and song info side by side
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        top_box.set_valign(Gtk.Align.START)

        # Album art on the left
        art_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # Replace Gtk.Image with Gtk.Picture
        self.album_art = Gtk.Picture()
        self.album_art.set_size_request(200, 200)
        self.album_art.set_can_shrink(False)
        self.album_art.set_keep_aspect_ratio(True)
        self.album_art.set_content_fit(Gtk.ContentFit.CONTAIN)
        art_box.append(self.album_art)
        top_box.append(art_box)

        # Song info on the right
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

        # Title
        self.title_label = Gtk.Label()
        self.title_label.add_css_class("title-2")
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self.title_label.set_max_width_chars(40)
        info_box.append(self.title_label)

        # Artist
        self.artist_label = Gtk.Label()
        self.artist_label.add_css_class("title-4")
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        info_box.append(self.artist_label)

        # Album with year
        album_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        album_box.set_halign(Gtk.Align.START)

        self.album_label = Gtk.Label()
        self.album_label.add_css_class("title-4")
        self.album_label.set_halign(Gtk.Align.START)
        self.album_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        album_box.append(self.album_label)

        self.year_label = Gtk.Label()
        self.year_label.add_css_class("title-4")
        self.year_label.set_halign(Gtk.Align.START)
        album_box.append(self.year_label)

        info_box.append(album_box)

        # Additional metadata in grid layout
        metadata_grid = Gtk.Grid()
        metadata_grid.set_column_spacing(12)
        metadata_grid.set_row_spacing(6)
        metadata_grid.set_margin_top(12)

        # Track info
        track_label = Gtk.Label(label="Track:")
        track_label.set_halign(Gtk.Align.START)
        track_label.add_css_class("dim-label")
        metadata_grid.attach(track_label, 0, 0, 1, 1)

        self.track_value = Gtk.Label()
        self.track_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.track_value, 1, 0, 1, 1)

        # Genre info
        genre_label = Gtk.Label(label="Genre:")
        genre_label.set_halign(Gtk.Align.START)
        genre_label.add_css_class("dim-label")
        metadata_grid.attach(genre_label, 0, 1, 1, 1)

        self.genre_value = Gtk.Label()
        self.genre_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.genre_value, 1, 1, 1, 1)

        # Format info
        format_label = Gtk.Label(label="Format:")
        format_label.set_halign(Gtk.Align.START)
        format_label.add_css_class("dim-label")
        metadata_grid.attach(format_label, 0, 2, 1, 1)

        self.format_value = Gtk.Label()
        self.format_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.format_value, 1, 2, 1, 1)

        # Codec info
        codec_label = Gtk.Label(label="Codec:")
        codec_label.set_halign(Gtk.Align.START)
        codec_label.add_css_class("dim-label")
        metadata_grid.attach(codec_label, 0, 3, 1, 1)

        self.codec_value = Gtk.Label()
        self.codec_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.codec_value, 1, 3, 1, 1)

        # Bitrate info
        bitrate_label = Gtk.Label(label="Bitrate:")
        bitrate_label.set_halign(Gtk.Align.START)
        bitrate_label.add_css_class("dim-label")
        metadata_grid.attach(bitrate_label, 0, 4, 1, 1)

        self.bitrate_value = Gtk.Label()
        self.bitrate_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.bitrate_value, 1, 4, 1, 1)

        # Length info
        length_label = Gtk.Label(label="Length:")
        length_label.set_halign(Gtk.Align.START)
        length_label.add_css_class("dim-label")
        metadata_grid.attach(length_label, 0, 5, 1, 1)

        self.length_value = Gtk.Label()
        self.length_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.length_value, 1, 5, 1, 1)

        info_box.append(metadata_grid)
        top_box.append(info_box)

        main_box.append(top_box)

        self.append(main_box)

        self.set_no_music_state()

    def set_no_music_state(self):
        """Set UI to 'no music' state"""
        self.title_label.set_text("No Music Playing")
        self.artist_label.set_text("Not Connected")
        self.album_label.set_text("")
        self.year_label.set_text("")
        self.track_value.set_text("")
        self.genre_value.set_text("")
        self.codec_value.set_text("")
        self.format_value.set_text("")
        self.bitrate_value.set_text("")
        self.length_value.set_text("")
        # Reset album art asynchronously
        AsyncUIHelper.run_async_operation(
            lambda: load_album_art(self.mpd_client, None, self.album_art, 200),
            None,  # No callback needed
        )

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        if self.mpd_client.current_song:
            GLib.idle_add(self.update_song_info)
        else:
            self.artist_label.set_text("Connected to MPD")

    def on_mpd_disconnected(self, client):
        """Handle MPD disconnection"""
        GLib.idle_add(self.set_no_music_state)

    def on_song_changed(self, client):
        """Handle song change"""
        GLib.idle_add(self.update_song_info)

    def on_state_changed(self, client):
        """Handle playback state change"""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        # Update UI elements that depend on the general state
        if "state" in status:
            _ = status["state"]
            # TODO: Make this do something

    def on_playback_status_changed(self, client, state):
        """Handle playback status changes (play, pause, stop)"""
        # You could update play/pause button states here if needed
        pass

    def on_bitrate_changed(self, client, bitrate):
        """Handle bitrate changes"""
        if self.mpd_client.current_song:
            self.bitrate_value.set_text(f"{bitrate} kbps")

    def update_song_info(self):
        """Update the song information display"""
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            self.set_no_music_state()
            return

        song = self.mpd_client.current_song
        print(song)  # Debugging output

        # Update labels
        self.title_label.set_text(song.get("title", song.get("file", "Unknown")))
        self.artist_label.set_text(song.get("artist", "Unknown Artist"))
        self.album_label.set_text(song.get("album", "Unknown Album"))

        # Extract and set year if available
        date = song.get("date", "")
        if date:
            # Try to extract just the year from date
            year_match = date.split("-")[0] if "-" in date else date
            self.year_label.set_text(f"({year_match})")
        else:
            self.year_label.set_text("")

        # Load album art
        AsyncUIHelper.run_async_operation(
            lambda: load_album_art(self.mpd_client, song, self.album_art, size=200),
            None,  # No callback needed
        )

        # Update metadata
        self.track_value.set_text(song.get("track", ""))
        self.genre_value.set_text(song.get("genre", ""))

        # Format duration as mm:ss
        if "time" in song:
            total_seconds = int(song["time"])
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            self.length_value.set_text(f"{minutes}:{seconds:02d}")
        else:
            self.length_value.set_text("")

        self.codec_value.set_text(song["file"].split(".")[-1].upper())

        # Set format value
        format = song.get("format", "")
        if format != "":
            format = format.split(":")[2] + " channels, " + format.split(":")[0] + " Hz"
        self.format_value.set_text(format)

    def on_prev_clicked(self, button):
        """Handle previous button click"""
        if self.mpd_client.is_connected():
            self.mpd_client.previous()

    def on_play_clicked(self, button):
        """Handle play/pause button click"""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        if status.get("state") == "play":
            self.mpd_client.pause()
        else:
            self.mpd_client.play()

    def on_next_clicked(self, button):
        """Handle next button click"""
        if self.mpd_client.is_connected():
            self.mpd_client.next()

    def on_repeat_toggled(self, button):
        """Handle repeat button toggle"""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_repeat()

    def on_random_toggled(self, button):
        """Handle random button toggle"""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_random()

    def on_single_toggled(self, button):
        """Handle single button toggle"""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_single()

    def on_consume_toggled(self, button):
        """Handle consume button toggle"""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_consume()

    def format_time(self, seconds):
        """Format seconds as mm:ss"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"
