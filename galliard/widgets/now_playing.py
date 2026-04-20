#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango  # noqa: E402

from galliard.utils.album_art import bind_art_to_widget  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402


class NowPlayingView(Gtk.Box):
    """Full-page now-playing view: art + song metadata grid."""

    def __init__(self, mpd_client):
        """Build the layout and subscribe to MPD state/song signals."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.mpd_client = mpd_client

        self.create_ui()

        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)
        self.mpd_client.connect_signal("state-changed", self.on_state_changed)

        # playback-status-changed fires independently of song-changed so the
        # UI picks up play/pause without waiting for the next song boundary.
        self.mpd_client.connect_signal(
            "playback-status-changed", self.on_playback_status_changed
        )
        self.mpd_client.connect_signal("bitrate-changed", self.on_bitrate_changed)

    def create_ui(self):
        """Build the art-on-the-left, info-on-the-right layout."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_vexpand(True)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_spacing(12)

        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        top_box.set_valign(Gtk.Align.START)

        art_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.album_art = Gtk.Picture()
        self.album_art.set_size_request(200, 200)
        self.album_art.set_can_shrink(False)
        self.album_art.set_content_fit(Gtk.ContentFit.CONTAIN)
        art_box.append(self.album_art)
        top_box.append(art_box)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

        self.title_label = Gtk.Label()
        self.title_label.add_css_class("title-2")
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_max_width_chars(40)
        info_box.append(self.title_label)

        self.artist_label = Gtk.Label()
        self.artist_label.add_css_class("title-4")
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(self.artist_label)

        album_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        album_box.set_halign(Gtk.Align.START)

        self.album_label = Gtk.Label()
        self.album_label.add_css_class("title-4")
        self.album_label.set_halign(Gtk.Align.START)
        self.album_label.set_ellipsize(Pango.EllipsizeMode.END)
        album_box.append(self.album_label)

        self.year_label = Gtk.Label()
        self.year_label.add_css_class("title-4")
        self.year_label.set_halign(Gtk.Align.START)
        album_box.append(self.year_label)

        info_box.append(album_box)

        # Metadata table: track, genre, format, codec, bitrate, length.
        metadata_grid = Gtk.Grid()
        metadata_grid.set_column_spacing(12)
        metadata_grid.set_row_spacing(6)
        metadata_grid.set_margin_top(12)

        track_label = Gtk.Label(label="Track:")
        track_label.set_halign(Gtk.Align.START)
        track_label.add_css_class("dim-label")
        metadata_grid.attach(track_label, 0, 0, 1, 1)

        self.track_value = Gtk.Label()
        self.track_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.track_value, 1, 0, 1, 1)

        genre_label = Gtk.Label(label="Genre:")
        genre_label.set_halign(Gtk.Align.START)
        genre_label.add_css_class("dim-label")
        metadata_grid.attach(genre_label, 0, 1, 1, 1)

        self.genre_value = Gtk.Label()
        self.genre_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.genre_value, 1, 1, 1, 1)

        format_label = Gtk.Label(label="Format:")
        format_label.set_halign(Gtk.Align.START)
        format_label.add_css_class("dim-label")
        metadata_grid.attach(format_label, 0, 2, 1, 1)

        self.format_value = Gtk.Label()
        self.format_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.format_value, 1, 2, 1, 1)

        codec_label = Gtk.Label(label="Codec:")
        codec_label.set_halign(Gtk.Align.START)
        codec_label.add_css_class("dim-label")
        metadata_grid.attach(codec_label, 0, 3, 1, 1)

        self.codec_value = Gtk.Label()
        self.codec_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.codec_value, 1, 3, 1, 1)

        bitrate_label = Gtk.Label(label="Bitrate:")
        bitrate_label.set_halign(Gtk.Align.START)
        bitrate_label.add_css_class("dim-label")
        metadata_grid.attach(bitrate_label, 0, 4, 1, 1)

        self.bitrate_value = Gtk.Label()
        self.bitrate_value.set_halign(Gtk.Align.START)
        metadata_grid.attach(self.bitrate_value, 1, 4, 1, 1)

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
        """Blank the metadata labels and reset the art widget."""
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
        bind_art_to_widget(self.mpd_client, self.album_art, None, 200)

    def on_mpd_connected(self, client):
        """Refresh the view on connect, or show a placeholder if nothing's playing."""
        if self.mpd_client.current_song:
            idle_add_once(self.update_song_info)
        else:
            self.artist_label.set_text("Connected to MPD")

    def on_mpd_disconnected(self, client):
        """Reset the view when MPD disconnects."""
        idle_add_once(self.set_no_music_state)

    def on_song_changed(self, client):
        """Refresh the whole view when the current song changes."""
        idle_add_once(self.update_song_info)

    def on_state_changed(self, client):
        """Hook for general state changes; currently unused."""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        if "state" in status:
            _ = status["state"]
            # TODO: Make this do something

    def on_playback_status_changed(self, client, state):
        """Hook for play/pause/stop transitions; currently unused."""
        pass

    def on_bitrate_changed(self, client, bitrate):
        """Update the bitrate label whenever MPD reports a new value."""
        if self.mpd_client.current_song:
            self.bitrate_value.set_text(f"{bitrate} kbps")

    def update_song_info(self):
        """Redraw the whole view from the current song's metadata."""
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            self.set_no_music_state()
            return

        song = self.mpd_client.current_song

        self.title_label.set_text(song.get("title", song.get("file", "Unknown")))
        self.artist_label.set_text(song.get("artist", "Unknown Artist"))
        self.album_label.set_text(song.get("album", "Unknown Album"))

        # MPD's date tag is typically "YYYY" but can be "YYYY-MM-DD".
        date = song.get("date", "")
        if date:
            year_match = date.split("-")[0] if "-" in date else date
            self.year_label.set_text(f"({year_match})")
        else:
            self.year_label.set_text("")

        bind_art_to_widget(self.mpd_client, self.album_art, song, 200)

        self.track_value.set_text(song.get("track", ""))
        self.genre_value.set_text(song.get("genre", ""))

        time_value = song.get("time")
        if time_value is not None:
            total_seconds = int(time_value)
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            self.length_value.set_text(f"{minutes}:{seconds:02d}")
        else:
            self.length_value.set_text("")

        # Codec from the file extension; MPD doesn't report it directly.
        self.codec_value.set_text(song.file.split(".")[-1].upper())

        # MPD's audio tag is "rate:bits:channels"; humanise the pieces we show.
        format = song.get("format", "")
        if format != "":
            format = format.split(":")[2] + " channels, " + format.split(":")[0] + " Hz"
        self.format_value.set_text(format)

    def on_prev_clicked(self, button):
        """Transport button: previous track."""
        if self.mpd_client.is_connected():
            self.mpd_client.previous()

    def on_play_clicked(self, button):
        """Transport button: toggle play/pause."""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        if status.get("state") == "play":
            self.mpd_client.pause()
        else:
            self.mpd_client.play()

    def on_next_clicked(self, button):
        """Transport button: next track."""
        if self.mpd_client.is_connected():
            self.mpd_client.next()

    def on_repeat_toggled(self, button):
        """Toggle MPD's repeat mode."""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_repeat()

    def on_random_toggled(self, button):
        """Toggle MPD's random mode."""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_random()

    def on_single_toggled(self, button):
        """Toggle MPD's single-song repeat mode."""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_single()

    def on_consume_toggled(self, button):
        """Toggle MPD's consume mode."""
        if self.mpd_client.is_connected():
            self.mpd_client.toggle_consume()
