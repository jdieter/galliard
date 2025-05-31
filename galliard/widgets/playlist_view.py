#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Adw, GLib, Pango  # noqa: E402

from galliard.models import Song  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402


class PlaylistView(Gtk.Box):
    """Playlist view widget for Galliard"""

    def __init__(self, mpd_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.mpd_client = mpd_client

        # Track keyboard modifiers
        self.current_modifiers = 0

        # Create UI
        self.create_ui()

        # Connect signals
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)
        self.mpd_client.connect_signal("playlist-changed", self.on_playlist_changed)
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)

    def on_key_pressed(self, controller, keyval, keycode, state):
        """Track modifier keys"""
        # For key press, we need to add the key to the state
        # We'll focus only on modifier keys
        modifier_mask = (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.ALT_MASK
        )

        # Handle modifier keys specifically
        if keyval == Gdk.KEY_Control_L or keyval == Gdk.KEY_Control_R:
            state |= Gdk.ModifierType.CONTROL_MASK
        elif keyval == Gdk.KEY_Shift_L or keyval == Gdk.KEY_Shift_R:
            state |= Gdk.ModifierType.SHIFT_MASK
        elif keyval == Gdk.KEY_Alt_L or keyval == Gdk.KEY_Alt_R:
            state |= Gdk.ModifierType.ALT_MASK

        # Update our tracked state
        self.current_modifiers = state & modifier_mask

    def on_key_released(self, controller, keyval, keycode, state):
        """Track modifier keys"""
        # For key release, we need to remove the key from the state
        modifier_mask = (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.ALT_MASK
        )

        # Handle modifier keys specifically
        if keyval == Gdk.KEY_Control_L or keyval == Gdk.KEY_Control_R:
            state &= ~Gdk.ModifierType.CONTROL_MASK
        elif keyval == Gdk.KEY_Shift_L or keyval == Gdk.KEY_Shift_R:
            state &= ~Gdk.ModifierType.SHIFT_MASK
        elif keyval == Gdk.KEY_Alt_L or keyval == Gdk.KEY_Alt_R:
            state &= ~Gdk.ModifierType.ALT_MASK

        # Update our tracked state
        self.current_modifiers = state & modifier_mask

    def create_ui(self):
        """Create the user interface"""
        # Create header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_box.add_css_class("toolbar")
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)
        header_box.set_margin_top(6)
        header_box.set_margin_bottom(6)

        # Add key controller to track modifier keys
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)

        # Playlist title
        playlist_label = Gtk.Label(
            label="Current Playlist", halign=Gtk.Align.START, hexpand=True
        )
        playlist_label.add_css_class("title-4")
        header_box.append(playlist_label)

        # Add playlist controls
        clear_button = Gtk.Button(
            icon_name="edit-clear-all-symbolic", tooltip_text="Clear playlist"
        )
        clear_button.connect("clicked", self.on_clear_playlist)
        header_box.append(clear_button)

        save_button = Gtk.Button(
            icon_name="document-save-symbolic", tooltip_text="Save playlist"
        )
        save_button.connect("clicked", self.on_save_playlist)
        header_box.append(save_button)

        self.append(header_box)

        # Create scrolled window for playlist
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # Create playlist view
        self.create_playlist_view()
        scrolled.set_child(self.playlist_view)

        self.append(scrolled)

        # Create statusbar
        statusbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=3,
            margin_start=6,
            margin_end=6,
            margin_top=3,
            margin_bottom=3,
        )

        self.status_label = Gtk.Label(label="0 songs, 0:00 total time")
        self.status_label.set_halign(Gtk.Align.START)
        statusbar.append(self.status_label)

        self.append(statusbar)

    def create_playlist_view(self):
        """Create the playlist view widget"""
        # Create list box instead of list view
        self.playlist_view = Gtk.ListBox()
        # Change to multiple selection mode
        self.playlist_view.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.playlist_view.add_css_class("boxed-list")

        # Track focus state
        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("enter", self.on_list_focus_enter)
        focus_controller.connect("leave", self.on_list_focus_leave)
        self.playlist_view.add_controller(focus_controller)

    def on_list_focus_enter(self, controller):
        """Handle list view focus enter"""
        self.list_has_focus = True

    def on_list_focus_leave(self, controller):
        """Handle list view focus leave"""
        self.list_has_focus = False

    def create_playlist_factory(self):
        """Create list item factory for playlist items"""
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_playlist_item_setup)
        factory.connect("bind", self.on_playlist_item_bind)
        return factory

    def on_playlist_item_setup(self, factory, list_item):
        """Set up playlist item widget"""
        # Create row with box layout
        row = Gtk.ListBoxRow()
        row.set_activatable(True)
        row.set_selectable(False)  # Don't use built-in selection highlighting

        # Store the list_item reference in the row for context menu
        row.list_item = list_item

        # Main container box
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=8,
        )

        # Left side container for number and play icon
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)

        # Number prefix
        row.number_label = Gtk.Label()
        row.number_label.add_css_class("dim-label")
        left_box.append(row.number_label)

        # Play indicator
        row.playing_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        row.playing_icon.set_opacity(0)  # Hidden by default
        left_box.append(row.playing_icon)

        box.append(left_box)

        # Text content box (vertical)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        content_box.set_hexpand(True)

        # Title
        row.title_label = Gtk.Label(xalign=0)
        row.title_label.add_css_class("title")
        row.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        row.title_label.set_max_width_chars(50)
        content_box.append(row.title_label)

        # Subtitle
        row.subtitle_label = Gtk.Label(xalign=0)
        row.subtitle_label.add_css_class("subtitle")
        row.subtitle_label.add_css_class("dim-label")
        row.subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
        content_box.append(row.subtitle_label)

        box.append(content_box)
        row.set_child(box)

        # Add to list item
        list_item.set_child(row)

        # Double-click handling
        click_controller = Gtk.GestureClick.new()
        click_controller.set_button(1)  # Left mouse button
        click_controller.connect("pressed", self.on_row_clicked, list_item)
        row.add_controller(click_controller)

        # Right-click handling
        right_click_controller = Gtk.GestureClick.new()
        right_click_controller.set_button(3)  # Right mouse button
        right_click_controller.connect("pressed", self.on_row_right_click, row)
        row.add_controller(right_click_controller)

    def on_playlist_item_bind(self, factory, list_item):
        """Bind playlist item data to widget"""
        row = list_item.get_child()
        song = list_item.get_item()
        position = list_item.get_position()

        # Set track number
        row.number_label.set_text(f"{position + 1}")

        # Set song title and artist
        title = song.get_title()
        artist = song.get_artist()
        album = song.get_album()

        row.title_label.set_text(GLib.markup_escape_text(title))
        row.subtitle_label.set_text(GLib.markup_escape_text(f"{artist} - {album}"))

        # Check if this is the current song
        if (
            self.mpd_client.is_connected()
            and self.mpd_client.current_song
            and self.mpd_client.current_song.get("id") == song.data.get("id")
        ):
            row.playing_icon.set_opacity(1)
        else:
            row.playing_icon.set_opacity(0)

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        AsyncUIHelper.run_async_operation(
            self.refresh_playlist, None  # No callback needed
        )

    def on_mpd_disconnected(self, client):
        """Handle MPD disconnection"""
        self.clear_playlist_view()

    def on_playlist_changed(self, client):
        """Handle playlist change"""
        AsyncUIHelper.run_async_operation(
            self.refresh_playlist, None  # No callback needed
        )

    def on_song_changed(self, client):
        """Handle song change - refresh the view to update playing indicator"""
        AsyncUIHelper.run_async_operation(
            self.refresh_playlist, None  # No callback needed
        )

    @AsyncUIHelper.run_in_background
    async def refresh_playlist(self):
        """Refresh the playlist view without clearing the entire list"""
        if not self.mpd_client.is_connected():
            self.clear_playlist_view()
            return

        print("Refreshing playlist...")
        # Get current playlist using async method
        new_playlist = await self.mpd_client.async_get_current_playlist()
        current_song_id = None

        if self.mpd_client.current_song:
            current_song_id = self.mpd_client.current_song.get("id")

        # Update UI in the main thread
        GLib.idle_add(self._update_playlist_ui, new_playlist, current_song_id)
        return False

    def _update_playlist_ui(self, new_playlist, current_song_id):
        """Update the playlist UI with new data - runs in main thread"""

        # Create dictionary of existing rows by their song ID
        existing_rows = {}
        row = self.playlist_view.get_first_child()
        while row:
            if hasattr(row, "song") and row.song.data.get("id") is not None:
                existing_rows[row.song.data.get("id")] = row
            row = row.get_next_sibling()

        # Build a new list of song IDs from the playlist
        new_song_ids = [song.get("id") for song in new_playlist]

        # Remove rows that are no longer in the playlist
        row = self.playlist_view.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            if hasattr(row, "song") and row.song.data.get("id") not in new_song_ids:
                self.playlist_view.remove(row)
            row = next_row

        # Update or add rows in the correct positions
        for i, song_data in enumerate(new_playlist):
            song_id = song_data.get("id")

            if song_id in existing_rows:
                # Update existing row
                row = existing_rows[song_id]
                row.position = i
                row.number_label.set_text(f"{i + 1}")

                # Reset play indicator (will set it if it's the current song)
                row.playing_icon.set_opacity(0)

                # Get current position by counting through siblings
                current_position = 0
                sibling = self.playlist_view.get_first_child()
                while sibling and sibling != row:
                    current_position += 1
                    sibling = sibling.get_next_sibling()

                # Move the row to the correct position if needed
                if current_position != i:
                    self.playlist_view.remove(row)
                    self.playlist_view.insert(row, i)
            else:
                # Add new row
                song = Song(song_data)
                row = self.create_playlist_row(song, i)
                self.playlist_view.insert(row, i)

            # Update the current playing song indicator
            if current_song_id and song_id == current_song_id:
                row.playing_icon.set_opacity(1)

        # Update status bar
        total_time = sum(float(song.get("time", 0)) for song in new_playlist)
        song_count = len(new_playlist)
        self.status_label.set_text(
            f"{song_count} {'song' if song_count == 1 else 'songs'}, "
            f"{self.format_time(total_time)} total time"
        )

        # Schedule scroll to the current song if we found it and not in focus
        # if current_row and not getattr(self, 'list_has_focus', False):
        #    GLib.idle_add(lambda: self.scroll_to_row(current_row))

        return False  # Remove from idle sources

    def clear_playlist_view(self):
        """Clear the playlist view"""
        while row := self.playlist_view.get_first_child():
            self.playlist_view.remove(row)
        self.status_label.set_text("0 songs, 0:00 total time")

    def format_time(self, seconds):
        """Format seconds as HH:MM:SS or MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    @AsyncUIHelper.run_in_background
    async def on_clear_playlist(self, button):
        """Handle clear playlist button"""
        if self.mpd_client.is_connected():
            await self.mpd_client.async_clear_playlist()

    def on_save_playlist(self, button):
        """Handle save playlist button"""
        if not self.mpd_client.is_connected():
            return

        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            title="Save Playlist",
            body="Enter a name for the playlist:",
        )

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        entry = Gtk.Entry()
        entry.set_margin_top(12)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)

        dialog.connect("response", self._on_save_playlist_response, entry)
        dialog.present()

    def _on_save_playlist_response(self, dialog, response_id, entry):
        """Handle save playlist dialog response"""
        if response_id == "save":
            playlist_name = entry.get_text().strip()
            if playlist_name:
                AsyncUIHelper.run_async_operation(
                    self.mpd_client.async_save_playlist, None, playlist_name
                )

    @AsyncUIHelper.run_in_background
    async def remove_selected_items(self, positions):
        """Remove multiple items from the playlist.

        Args:
            positions: List of playlist positions to remove
        """
        if not self.mpd_client.is_connected():
            return

        # Sort positions in descending order to avoid index shifting
        positions.sort(reverse=True)

        for position in positions:
            await self.mpd_client.async_delete(position)

        # No need to refresh playlist here as the playlist-changed signal will trigger a refresh

    def on_row_right_click(self, gesture, n_press, x, y, row):
        """Handle right-click on a playlist row"""
        if not self.mpd_client.is_connected():
            return

        # Get the currently selected rows
        selected_rows = self.playlist_view.get_selected_rows()

        # If the right-clicked row is not in the selection, select only this row
        if row not in selected_rows:
            self.playlist_view.unselect_all()
            self.playlist_view.select_row(row)
            selected_rows = [row]

        # Get positions of all selected rows
        selected_positions = [r.position for r in selected_rows]

        # Determine the last selected row for play action
        last_selected_position = (
            selected_positions[-1] if selected_positions else row.position
        )

        # Create menu items
        menu_items = [
            {
                "label": "Play Selected",
                "action": "play-selection",
                "callback": lambda: self._play_selected_item(last_selected_position),
            },
            {
                "label": f"Remove Selected ({len(selected_positions)})",
                "action": "remove-selection",
                "callback": lambda: self.remove_selected_items(selected_positions),
            },
        ]

        # Show the context menu
        ContextMenu.create_menu_with_actions(
            row,  # Parent widget
            menu_items,  # Menu items
            "row",  # Action group name
            x,  # X position
            y,  # Y position
        )

    def on_row_clicked(self, gesture, n_press, x, y, list_item):
        """Handle click on a playlist row"""
        row = None
        if isinstance(list_item, Gtk.ListBoxRow):
            row = list_item
        else:
            row = list_item.get_child()

        # Handle double-click for playback
        if n_press == 2:
            self.on_playlist_item_activated(self.playlist_view, row)
            return

        # Get modifier state from our tracked state
        shift_pressed = (self.current_modifiers & Gdk.ModifierType.SHIFT_MASK) != 0
        ctrl_pressed = (self.current_modifiers & Gdk.ModifierType.CONTROL_MASK) != 0

        # Store last clicked row for Shift+click range selection
        if not hasattr(self, "last_selected_row"):
            self.last_selected_row = None

        if shift_pressed and self.last_selected_row:
            # Range selection with Shift
            start_pos = self.last_selected_row.position
            end_pos = row.position

            # Ensure start is before end
            if start_pos > end_pos:
                start_pos, end_pos = end_pos, start_pos

            # First clear selection if Ctrl is not pressed
            if not ctrl_pressed:
                self.playlist_view.unselect_all()

            # Select all rows in the range
            current_row = self.playlist_view.get_first_child()
            pos = 0
            while current_row:
                if start_pos <= pos <= end_pos:
                    self.playlist_view.select_row(current_row)
                pos += 1
                current_row = current_row.get_next_sibling()

        elif ctrl_pressed:
            # Toggle selection with Ctrl
            if self.playlist_view.is_selected(row):
                self.playlist_view.unselect_row(row)
            else:
                self.playlist_view.select_row(row)
            self.last_selected_row = row

        else:
            # Regular click - select only this row
            self.playlist_view.unselect_all()
            self.playlist_view.select_row(row)
            self.last_selected_row = row

    def create_playlist_row(self, song, position):
        """Create a row for a playlist item"""
        row = Gtk.ListBoxRow()
        row.set_activatable(True)
        row.set_selectable(True)

        # Store the song data in the row
        row.song = song
        row.position = position

        # Main container box
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=8,
        )

        # Left side container for number and play icon
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)

        # Number prefix
        row.number_label = Gtk.Label(label=f"{position + 1}")
        row.number_label.add_css_class("dim-label")
        left_box.append(row.number_label)

        # Play indicator
        row.playing_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        row.playing_icon.set_opacity(0)  # Hidden by default
        left_box.append(row.playing_icon)

        box.append(left_box)

        # Text content box (vertical)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        content_box.set_hexpand(True)

        # Title
        title = song.get_title()
        row.title_label = Gtk.Label(label=title, xalign=0)
        row.title_label.add_css_class("title")
        row.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        row.title_label.set_max_width_chars(50)
        content_box.append(row.title_label)

        # Subtitle
        artist = song.get_artist()
        album = song.get_album()
        row.subtitle_label = Gtk.Label(label=f"{artist} - {album}", xalign=0)
        row.subtitle_label.add_css_class("subtitle")
        row.subtitle_label.add_css_class("dim-label")
        row.subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
        content_box.append(row.subtitle_label)

        box.append(content_box)
        row.set_child(box)

        # Left-click handling
        click_controller = Gtk.GestureClick.new()
        click_controller.set_button(1)
        click_controller.connect("pressed", self.on_row_clicked, row)
        row.add_controller(click_controller)

        # Right-click handling
        right_click_controller = Gtk.GestureClick.new()
        right_click_controller.set_button(3)  # Right mouse button
        right_click_controller.connect("pressed", self.on_row_right_click, row)
        row.add_controller(right_click_controller)

        return row

    def on_playlist_item_activated(self, listbox, row):
        """Handle playlist item activation"""
        if self.mpd_client.is_connected():
            position = row.position
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_play, None, position
            )

    def scroll_to_row(self, row):
        """Scroll to make a specific row visible with smooth animation"""
        # Only scroll if the list doesn't have focus
        if hasattr(self, "list_has_focus") and self.list_has_focus:
            return

        # Get scrolled window parent
        scrolled_window = self.playlist_view.get_parent()
        if not scrolled_window:
            return

        # Get the adjustment
        adj = scrolled_window.get_vadjustment()
        if not adj:
            return

        # Get the allocation rectangle for the row
        rect = row.get_allocation()
        if not rect:
            return

        # Calculate start and target positions
        start_value = adj.get_value()
        target_value = rect.y

        # Define animation parameters
        duration = 500  # Animation duration in milliseconds
        fps = 60  # Frames per second
        total_frames = int(duration / (1000 / fps))

        # Start the animation
        self._animate_scroll(adj, start_value, target_value, total_frames, 0)

    def _animate_scroll(
        self, adj, start_value, target_value, total_frames, current_frame
    ):
        """Perform smooth scrolling animation with exponential easing"""
        if current_frame > total_frames:
            return False

        # Calculate progress (0.0 to 1.0)
        t = current_frame / total_frames

        # Apply exponential ease-in and ease-out
        # This creates a smooth acceleration and deceleration effect
        if t < 0.5:
            # Ease in (exponential)
            progress = 2 * t * t
        else:
            # Ease out (exponential)
            t = t * 2 - 1
            progress = 1 - (1 - t) * (1 - t)

        # Calculate the new position
        new_value = start_value + (target_value - start_value) * progress

        # Set the adjustment value
        adj.set_value(new_value)

        # Schedule the next frame
        if current_frame < total_frames:
            GLib.timeout_add(
                int(1000 / 60),
                self._animate_scroll,
                adj,
                start_value,
                target_value,
                total_frames,
                current_frame + 1,
            )

        return False  # Remove from idle sources
