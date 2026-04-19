#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

from galliard.utils.album_art import bind_art_to_widget  # noqa: E402
from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402


class PlayerControls(Gtk.Box):
    """Always-visible playback strip: art, song info, transport, volume."""

    def __init__(self, mpd_client):
        """Build the controls, subscribe to MPD signals, and wire up teardown."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("player-controls")

        self.mpd_client = mpd_client
        self._volume_timeout_id = None
        self._progress_timer_id = None

        self.create_ui()

        # Stop the progress timer when the widget is torn down so the
        # callback can't fire against destroyed widgets.
        self.connect("unrealize", self._on_unrealize)

        self.mpd_client.connect_signal("disconnecting-blocked", self.reset_controls)
        self.mpd_client.connect_signal("disconnected", self.reset_controls)
        self.mpd_client.connect_signal("connecting-blocked", self.reset_controls)
        self.mpd_client.connect_signal("connecting", self.reset_controls)
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("state-changed", self.on_state_changed)
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)
        self.mpd_client.connect_signal("volume-changed", self.on_volume_changed)
        self.mpd_client.connect_signal("elapsed-changed", self.on_elapsed_changed)
        self.mpd_client.connect_signal("repeat-changed", self.on_repeat_changed)
        self.mpd_client.connect_signal("random-changed", self.on_random_changed)

    def create_ui(self):
        """Build the horizontal strip: art | song info | progress | controls | volume."""
        self.main_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=6
        )
        self.append(self.main_box)

        self.album_image = Gtk.Picture()
        self.album_image.set_size_request(50, 50)
        self.album_image.set_content_fit(Gtk.ContentFit.COVER)
        self.album_image.add_css_class("rounded")
        self.main_box.append(self.album_image)

        self.create_song_info_section()
        self.create_progress_section()
        self.create_control_buttons()
        self.create_volume_control()

        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Add CSS for error message styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(
            """
            .error-title {
                color: #ed333b;
                font-weight: bold;
            }
        """
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def create_song_info_section(self):
        """Create detailed song information section"""
        # Song info container
        song_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        song_info_box.set_margin_start(8)
        song_info_box.set_margin_end(8)
        song_info_box.set_margin_top(4)
        song_info_box.set_margin_bottom(4)
        self.main_box.append(song_info_box)

        # Song title using Adw.WindowTitle would be too heavy, keep simple label
        self.song_title_label = Gtk.Label(label="Not playing", xalign=0, ellipsize=Pango.EllipsizeMode.END, hexpand=True)
        self.song_title_label.add_css_class("title-4")
        song_info_box.append(self.song_title_label)

        # Artist with "By" prefix
        artist_album_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, halign=Gtk.Align.START, hexpand=True)

        self.artist_prefix = Gtk.Label(label="")
        self.artist_prefix.add_css_class("dim-label")
        artist_album_box.append(self.artist_prefix)

        self.song_artist_label = Gtk.Label(label="", ellipsize=Pango.EllipsizeMode.END)
        artist_album_box.append(self.song_artist_label)

        # Album
        self.album_prefix = Gtk.Label(label="")
        self.album_prefix.add_css_class("dim-label")
        artist_album_box.append(self.album_prefix)

        self.song_album_label = Gtk.Label(label="", ellipsize=Pango.EllipsizeMode.END)
        artist_album_box.append(self.song_album_label)

        song_info_box.append(artist_album_box)

    def create_progress_section(self):
        """Create progress bar and time labels"""
        # Progress container
        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        progress_box.set_hexpand(True)
        progress_box.set_size_request(100, -1)  # Set minimum width to 100 pixels
        self.main_box.append(progress_box)

        # Progress bar
        self.progress_bar = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=100, step_increment=1),
        )
        self.progress_bar.set_draw_value(False)
        self.progress_bar.connect("change-value", self.on_progress_change_value)
        progress_box.append(self.progress_bar)

        # Time labels (moved below progress bar)
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER)

        self.elapsed_label = Gtk.Label(label="0:00")
        time_box.append(self.elapsed_label)
        time_box.append(Gtk.Label(label="/"))
        self.total_label = Gtk.Label(label="0:00")
        time_box.append(self.total_label)

        progress_box.append(time_box)

        # Update timer
        self._progress_timer_id = GLib.timeout_add(1000, self.update_progress)

    def create_control_buttons(self):
        """Create playback control buttons"""
        # Control buttons container
        control_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=2, halign=Gtk.Align.CENTER
        )

        # Previous button
        self.prev_button = Gtk.Button(icon_name="media-skip-backward-symbolic")
        self.prev_button.connect("clicked", self.on_prev_clicked)
        control_box.append(self.prev_button)

        # Play/Pause button
        self.play_button = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.play_button.connect("clicked", self.on_play_clicked)
        control_box.append(self.play_button)

        # Stop button
        self.stop_button = Gtk.Button(icon_name="media-playback-stop-symbolic")
        self.stop_button.connect("clicked", self.on_stop_clicked)
        control_box.append(self.stop_button)

        # Next button
        self.next_button = Gtk.Button(icon_name="media-skip-forward-symbolic")
        self.next_button.connect("clicked", self.on_next_clicked)
        control_box.append(self.next_button)

        # Add a separator
        control_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=6, margin_end=6))

        # Repeat button
        if self.mpd_client.is_connected():
            repeat = self.mpd_client.status.get("repeat", "0") == "1"
            single = self.mpd_client.status.get("single", "0") == "1"
            random = self.mpd_client.status.get("random", "0") == "1"
        else:
            repeat = False
            single = False
            random = False

        self.repeat_button = Gtk.Button(icon_name="media-playlist-repeat-symbolic")
        self.repeat_button.connect("clicked", self.on_repeat_clicked)
        if self.mpd_client.is_connected():
            self.on_repeat_changed(self.mpd_client, repeat, single)
        control_box.append(self.repeat_button)

        # Random (shuffle) button
        self.random_button = Gtk.Button(icon_name="media-playlist-consecutive-symbolic")
        self.random_button.connect("clicked", self.on_random_clicked)
        if self.mpd_client.is_connected():
            self.on_random_changed(self.mpd_client, random)
        control_box.append(self.random_button)

        self.main_box.append(control_box)

        # Add CSS for enabled mode buttons
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(
            """
            button.enabled-mode {
                color: @accent_color;
            }
        """
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def create_volume_control(self):
        """Create volume control with horizontal lines"""
        volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_start=6)

        # Container for the line indicators
        lines_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.END)
        lines_container.set_size_request(50, -1)

        # Create the five volume level indicators (lines)
        self.volume_lines = []
        for i in range(7):
            width = 50 - (i * 6)  # Decrease by 6px for each line
            line_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END)
            line_box.set_size_request(width, 6)
            line_box.add_css_class("volume-line")
            line_box.add_css_class("volume-line-inactive")
            lines_container.append(line_box)
            self.volume_lines.append(line_box)

        # Reverse the list so index 0 is the bottom line
        self.volume_lines.reverse()

        volume_box.append(lines_container)

        # Create a hidden scale for handling the actual volume value
        self.volume_scale = Gtk.Scale(
            orientation=Gtk.Orientation.VERTICAL,
            adjustment=Gtk.Adjustment(value=50, lower=0, upper=100, step_increment=1),
        )
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_opacity(0)  # Hidden but functional

        # Gesture controller for the lines container
        click_controller = Gtk.GestureClick.new()
        click_controller.connect("pressed", self.on_volume_lines_clicked)
        lines_container.add_controller(click_controller)

        drag_controller = Gtk.GestureDrag.new()
        drag_controller.connect("drag-update", self.on_volume_lines_dragged)
        lines_container.add_controller(drag_controller)

        # Add both to the volume box
        volume_box.append(self.volume_scale)

        self.main_box.append(volume_box)

        # Add CSS for styling the volume lines
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(
            """
            .volume-line {
                background-color: @accent_bg_color;
                border-radius: 3px;
            }
            .volume-line-inactive {
                background-color: alpha(@accent_bg_color, 0.3);
            }
            .volume-line-disabled {
                background-color: alpha(@accent_bg_color, 0.1);
            }
        """
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_prev_clicked(self, button):
        """Handle previous button click"""
        AsyncUIHelper.run_async_operation(
            self.mpd_client.async_previous,  # Use async method directly instead of wrapper
            self.update_after_playback_action,  # Callback to update UI
        )

    def update_after_playback_action(self, result):
        """Update UI after a playback action completes"""
        # This method will be called in the GTK main thread after the async operation
        self.update_play_button_state()

    def update_play_button_state(self):
        """Update play button icon based on current state"""
        if not self.mpd_client.is_connected():
            self.play_button.set_icon_name("media-playback-start-symbolic")
            return

        state = self.mpd_client.status.get("state", "stop")
        if state == "play":
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

    def on_play_clicked(self, button):
        """Handle play/pause button click"""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        if status.get("state") == "play":
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_pause, self.update_after_playback_action
            )
        else:
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_play, self.update_after_playback_action
            )

    def on_stop_clicked(self, button):
        """Handle stop button click"""
        if not self.mpd_client.is_connected():
            return

        AsyncUIHelper.run_async_operation(
            self.mpd_client.async_stop, self.update_after_playback_action
        )

    def on_next_clicked(self, button):
        """Handle next button click"""
        if not self.mpd_client.is_connected():
            return

        AsyncUIHelper.run_async_operation(
            self.mpd_client.async_next, self.update_after_playback_action
        )

    def on_repeat_clicked(self, button):
        """Handle repeat button click to cycle through three modes:
        1. No repeat (default)
        2. Repeat playlist
        3. Repeat single song
        """
        if not self.mpd_client.is_connected():
            return

        # Get current repeat/single status
        current_repeat = self.mpd_client.status.get("repeat", "0")
        current_single = self.mpd_client.status.get("single", "0")

        # Cycle through the three states
        if current_repeat == "0" and current_single == "0":
            # State 1 -> State 2: Enable repeat playlist
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_repeat,
                None,  # No callback needed as signals will handle this
                "1",
            )
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_single,
                None,  # No callback needed as signals will handle this
                "0",
            )
        elif current_repeat == "1" and current_single == "0":
            # State 2 -> State 3: Enable repeat single
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_repeat,
                None,  # No callback needed as signals will handle this
                "1",
            )
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_single,
                None,  # No callback needed as signals will handle this
                "1",
            )
        else:
            # State 3 -> State 1: Disable all repeat
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_repeat,
                None,  # No callback needed as signals will handle this
                "0",
            )
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_single,
                None,  # No callback needed as signals will handle this
                "0",
            )

    def on_random_clicked(self, button):
        """Toggle random (shuffle) mode"""
        if not self.mpd_client.is_connected():
            return

        # Get current random status
        current_random = self.mpd_client.status.get("random", "0")

        # Toggle random mode
        if current_random == "0":
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_random,
                None,  # No callback needed as signals will handle this
                "1",
            )
        else:
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_random,
                None,  # No callback needed as signals will handle this
                "0",
            )

    def on_progress_change_value(self, scale, scroll_type, value):
        """Handle progress bar change"""
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            return False

        total_time = float(self.mpd_client.current_song.get("time", 0))
        if total_time > 0:
            seek_time = (value / 100.0) * total_time
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_seek,
                None,  # No callback needed as elapsed-changed signal will update UI
                seek_time,
            )
        return False

    def on_volume_scale_changed(self, scale):
        """Handle volume scale change"""
        if not self.mpd_client.is_connected():
            return

        volume = int(scale.get_value())

        # Update the volume lines immediately
        self.update_volume_lines(volume)

        # Debounce volume changes to avoid excessive MPD commands
        if hasattr(self, "_volume_timeout_id") and self._volume_timeout_id:
            GLib.source_remove(self._volume_timeout_id)

        # Set a short timeout before sending the volume command
        self._volume_timeout_id = GLib.timeout_add(
            100, self._send_volume_command, volume  # 100ms debounce
        )

    def _send_volume_command(self, volume):
        """Send volume command to MPD after debouncing"""
        AsyncUIHelper.run_async_operation(
            self.mpd_client.async_set_volume,
            None,  # No callback needed as signal will handle this
            volume,
        )
        self._volume_timeout_id = None  # Clear the timeout ID
        return False  # Don't call again

    def on_volume_lines_clicked(self, gesture, n_press, x, y):
        """Handle click on volume lines"""
        if not self.mpd_client.is_connected():
            return

        # Calculate which segment was clicked
        lines_height = len(self.volume_lines) * 8  # Approx height of all lines
        if y < 0 or y > lines_height:
            return

        # Calculate volume percentage based on click position
        volume_percent = (1 - (y / lines_height)) * 100
        self.volume_scale.set_value(volume_percent)

        # Update MPD volume
        volume = int(volume_percent)
        AsyncUIHelper.run_async_operation(
            self.mpd_client.async_set_volume,
            None,  # No callback needed as signals will handle this
            volume,
        )

    def on_volume_lines_dragged(self, gesture, offset_x, offset_y):
        """Handle drag on volume lines"""
        if not self.mpd_client.is_connected():
            return

        # Get the current value
        current_value = self.volume_scale.get_value()

        # Convert vertical movement to volume change (invert so up = louder)
        volume_change = -offset_y / 2  # Adjust sensitivity
        new_value = max(0, min(100, current_value + volume_change))

        # Set the new volume
        self.volume_scale.set_value(new_value)

        # Update the volume lines immediately
        self.update_volume_lines(int(new_value))

        # Only update MPD volume when dragging ends to avoid excessive commands
        if gesture.get_current_button() == 0:  # Button released
            volume = int(new_value)
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_set_volume,
                None,  # No callback needed as signals will handle this
                volume,
            )

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        self.clear_connection_error()
        self.update_controls_sensitivity(True)

        if self.mpd_client.current_song:
            self.on_song_changed(client)

        if "volume" in self.mpd_client.status:
            try:
                volume = int(self.mpd_client.status["volume"])
                self.volume_scale.set_value(volume)
                self.update_volume_lines(volume)
            except (ValueError, TypeError):
                pass

        return True  # Continue updating

    def format_time(self, seconds):
        """Format seconds as mm:ss"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"

    def on_state_changed(self, client):
        """Handle playback state change"""
        if not self.mpd_client.is_connected():
            self.play_button.set_icon_name("media-playback-start-symbolic")
            return

        status = self.mpd_client.status
        state = status.get("state", "stop")

        if state == "play":
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

        if state == "stop":
            # Reset elapsed time and progress bar when stopped
            self.elapsed_label.set_text("0:00")
            self.progress_bar.set_value(0)

        # Update volume
        try:
            volume = int(status.get("volume", 50))
            self.volume_scale.set_value(volume)
        except (ValueError, TypeError):
            pass

    def on_song_changed(self, client):
        """Handle song change"""
        song = None
        if self.mpd_client.is_connected() and self.mpd_client.current_song:
            song = self.mpd_client.current_song
            title = song.get("title", "Unknown")
            artist = song.get("artist", "Unknown")
            album = song.get("album", "Unknown")
            date = song.get("date", None)

            if date is not None:
                album += f" ({date})"
            # Update the detailed song information
            self.song_title_label.set_text(title)
            self.artist_prefix.set_text("By")
            self.song_artist_label.set_text(artist)
            self.album_prefix.set_text("from")
            self.song_album_label.set_text(album)
        else:
            self.song_title_label.set_text("Not playing")
            self.artist_prefix.set_text("")
            self.song_artist_label.set_text("")
            self.album_prefix.set_text("")
            self.song_album_label.set_text("")

        bind_art_to_widget(self.mpd_client, self.album_image, song, 50)

    def on_repeat_changed(self, client, repeat, single):
        """Update the repeat button icon to match MPD's ``repeat`` + ``single`` state."""
        if not hasattr(self, "repeat_button"):
            return

        if repeat and single:
            self.repeat_button.set_icon_name("media-playlist-repeat-song-symbolic")
            self.repeat_button.add_css_class("enabled-mode")
        elif repeat:
            self.repeat_button.set_icon_name("media-playlist-repeat-symbolic")
            self.repeat_button.add_css_class("enabled-mode")
        else:
            self.repeat_button.set_icon_name("media-playlist-repeat-symbolic")
            self.repeat_button.remove_css_class("enabled-mode")

    def on_random_changed(self, client, random):
        """Update the shuffle button icon to match MPD's ``random`` state."""
        if not hasattr(self, "random_button"):
            return

        if random:
            self.random_button.set_icon_name("media-playlist-shuffle-symbolic")
            self.random_button.add_css_class("enabled-mode")
        else:
            self.random_button.set_icon_name("media-playlist-consecutive-symbolic")
            self.random_button.remove_css_class("enabled-mode")

    def reset_controls(self, client=None):
        """Reset all controls to their initial state"""
        # Reset song title and artist/album info
        self.song_title_label.set_text("Not playing")
        self.artist_prefix.set_text("")
        self.song_artist_label.set_text("")
        self.album_prefix.set_text("")
        self.song_album_label.set_text("")

        bind_art_to_widget(self.mpd_client, self.album_image, None, 50)

        # Reset progress bar and time labels
        self.progress_bar.set_value(0)
        self.elapsed_label.set_text("0:00")
        self.total_label.set_text("0:00")

        # Reset control buttons
        self.play_button.set_icon_name("media-playback-start-symbolic")
        self.update_controls_sensitivity(False)

        # Reset repeat button
        self.repeat_button.set_icon_name("media-playlist-repeat-symbolic")
        self.repeat_button.remove_css_class("enabled-mode")

        # Reset random button
        self.random_button.remove_css_class("enabled-mode")

    def show_connection_error(self, error_message):
        """Display connection error in the title area"""
        # Store the error message
        self.error_message = error_message

        self.reset_controls()

        # Update the song title to show the error
        self.song_title_label.set_text(f"Connection Error: {error_message}")
        self.song_title_label.add_css_class("error-title")

    def clear_connection_error(self):
        """Clear any displayed connection error"""
        if hasattr(self, "error_message"):
            self.error_message = None
            self.song_title_label.remove_css_class("error-title")

            # Restore normal display
            if self.mpd_client.current_song:
                self.on_song_changed(self.mpd_client)
            else:
                self.song_title_label.set_text("Not playing")

    def update_controls_sensitivity(self, sensitive):
        """Enable or disable playback control buttons"""
        # Update all control buttons
        self.prev_button.set_sensitive(sensitive)
        self.play_button.set_sensitive(sensitive)
        self.stop_button.set_sensitive(sensitive)
        self.next_button.set_sensitive(sensitive)
        self.repeat_button.set_sensitive(sensitive)
        self.random_button.set_sensitive(sensitive)

    def _on_unrealize(self, widget):
        """Cancel the progress timer when the widget is unrealized"""
        if self._progress_timer_id is not None:
            GLib.source_remove(self._progress_timer_id)
            self._progress_timer_id = None

    def update_progress(self):
        """Update progress bar and time labels every second"""
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            return True  # Continue timer

        try:
            status = self.mpd_client.status
            if status.get("state") != "play":
                return True  # Continue timer even if not playing

            elapsed = float(status.get("elapsed", 0))
            total = float(self.mpd_client.current_song.get("time", 0))

            if total > 0:
                # Update progress bar
                percent = (elapsed / total) * 100
                self.progress_bar.set_value(percent)

                # Update time labels
                elapsed_str = self.format_time(elapsed)
                total_str = self.format_time(total)
                self.elapsed_label.set_text(elapsed_str)
                self.total_label.set_text(total_str)

        except (ValueError, TypeError, KeyError) as e:
            # Handle any errors gracefully
            print(f"Error updating progress: {e}")

        return True  # Continue timer

    def on_volume_changed(self, client, volume):
        """Update the scale + LED display to match MPD's reported volume."""
        try:
            volume = int(volume)
            self.volume_scale.set_value(volume)
            self.update_volume_lines(volume)
        except (ValueError, TypeError):
            pass

    def update_volume_lines(self, volume):
        """Redraw the LED-bar volume indicator for a 0-100 ``volume``."""
        if not hasattr(self, "volume_lines"):
            return

        total_lines = len(self.volume_lines)
        active_lines = int(round((volume / 100.0) * total_lines))

        for i, line in enumerate(self.volume_lines):
            if self.mpd_client.is_connected():
                if i < active_lines:
                    line.remove_css_class("volume-line-inactive")
                    line.remove_css_class("volume-line-disabled")
                    line.add_css_class("volume-line")
                else:
                    line.remove_css_class("volume-line")
                    line.remove_css_class("volume-line-disabled")
                    line.add_css_class("volume-line-inactive")
            else:
                # Grey out every segment when MPD is unreachable.
                line.remove_css_class("volume-line")
                line.remove_css_class("volume-line-inactive")
                line.add_css_class("volume-line-disabled")

    def on_elapsed_changed(self, client, elapsed):
        """Redraw the progress bar and time labels for a new elapsed time."""
        if not self.mpd_client.is_connected() or not self.mpd_client.current_song:
            return

        try:
            elapsed = float(elapsed)
            total = float(self.mpd_client.current_song.get("time", 0))

            if total > 0:
                percent = (elapsed / total) * 100
                self.progress_bar.set_value(percent)

                elapsed_str = self.format_time(elapsed)
                total_str = self.format_time(total)
                self.elapsed_label.set_text(elapsed_str)
                self.total_label.set_text(total_str)
        except (ValueError, TypeError):
            pass
