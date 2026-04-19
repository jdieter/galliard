#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Adw, GLib  # noqa: E402

from galliard.models import Song  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402


class PlaylistView(Gtk.Box):
    """Playlist view widget for Galliard"""

    def __init__(self, mpd_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.mpd_client = mpd_client

        # Track keyboard modifiers
        self.current_modifiers = 0

        self._scroll_animation_id = None

        # Create UI
        self.create_ui()

        # Connect signals
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)
        self.mpd_client.connect_signal("playlist-changed", self.on_playlist_changed)
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)

        # Stop the scroll animation when the widget is torn down so the
        # callback can't fire against destroyed widgets.
        self.connect("unrealize", self._on_unrealize)

    def _on_unrealize(self, widget):
        """Cancel any in-flight scroll animation when the widget is unrealized"""
        if self._scroll_animation_id:
            GLib.source_remove(self._scroll_animation_id)
            self._scroll_animation_id = None

    def _update_modifier_state(self, keyval, state, is_press):
        """Update modifier state for both press and release events"""
        modifier_mask = (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.ALT_MASK
        )

        # Handle modifier keys specifically
        if keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R):
            if is_press:
                state |= Gdk.ModifierType.CONTROL_MASK
            else:
                state &= ~Gdk.ModifierType.CONTROL_MASK
        elif keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            if is_press:
                state |= Gdk.ModifierType.SHIFT_MASK
            else:
                state &= ~Gdk.ModifierType.SHIFT_MASK
        elif keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R):
            if is_press:
                state |= Gdk.ModifierType.ALT_MASK
            else:
                state &= ~Gdk.ModifierType.ALT_MASK

        # Update our tracked state
        self.current_modifiers = state & modifier_mask

    def on_key_pressed(self, controller, keyval, keycode, state):
        """Track modifier keys"""
        self._update_modifier_state(keyval, state, True)

    def on_key_released(self, controller, keyval, keycode, state):
        """Track modifier keys"""
        self._update_modifier_state(keyval, state, False)

    def create_ui(self):
        """Create the user interface"""
        # Create header using Adwaita HeaderBar
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Gtk.Label(label="Current Playlist"))
        header_bar.add_css_class("flat")
        header_bar.set_show_end_title_buttons(False)  # Remove close button and other window controls

        # Add key controller to track modifier keys
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)

        # Add playlist controls to header bar
        clear_button = Gtk.Button(
            icon_name="edit-clear-all-symbolic", tooltip_text="Clear playlist"
        )
        clear_button.connect("clicked", self.on_clear_playlist)
        header_bar.pack_end(clear_button)

        #save_button = Gtk.Button(
        #    icon_name="document-save-symbolic", tooltip_text="Save playlist"
        #)
        #save_button.connect("clicked", self.on_save_playlist)
        #header_bar.pack_end(save_button)

        self.append(header_bar)

        # Create scrolled window for playlist
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # Create playlist view
        self.create_playlist_view()
        scrolled.set_child(self.playlist_view)

        self.append(scrolled)

        # Create statusbar using Adw.StatusPage for empty state or regular box for content
        self.status_page = Adw.StatusPage()
        self.status_page.set_title("No Songs")
        self.status_page.set_description("Your playlist is empty")
        self.status_page.set_icon_name("folder-music-symbolic")

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
        # Create list box with Adwaita styling
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
        # Create row with Adwaita action row
        row = Adw.ActionRow()
        row.set_activatable(True)

        # Store the list_item reference in the row for context menu
        setattr(row, "list_item", list_item)

        # Create the common row elements
        self._setup_row_elements(row)

        # Add to list item
        list_item.set_child(row)

        # Setup event controllers
        self._setup_row_controllers(row, list_item)

    def on_playlist_item_bind(self, factory, list_item):
        """Bind playlist item data to widget"""
        row = list_item.get_child()
        song = list_item.get_item()
        position = list_item.get_position()

        # Use the helper method
        self._bind_song_data_to_row(row, song, position)

        # Check if this is the current song
        if (
            self.mpd_client.is_connected()
            and self.mpd_client.current_song
            and self.mpd_client.current_song.get("id") == song.data.get("id")
        ):
            row.playing_icon.set_opacity(1)
        else:
            row.playing_icon.set_opacity(0)

    def _setup_row_elements(self, row):
        """Setup common row elements (album art, number label, play icon, etc.)"""
        # Left side container for album art, number and play icon
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Number prefix and play icon container
        number_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)

        # Play indicator
        playing_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        playing_icon.set_opacity(0)  # Hidden by default
        number_box.append(playing_icon)
        setattr(row, "playing_icon", playing_icon)

        # Number prefix
        label = Gtk.Label()
        label.add_css_class("dim-label")
        label.add_css_class("numeric")
        number_box.append(label)
        setattr(row, "number_label", label)

        left_box.append(number_box)

        # Album art
        album_art = Gtk.Image()
        album_art.set_size_request(40, 40)
        album_art.set_pixel_size(40)
        album_art.set_from_icon_name("audio-x-generic-symbolic")

        left_box.append(album_art)
        setattr(row, "album_art", album_art)

        row.add_prefix(left_box)

    def _setup_row_controllers(self, row, list_item_or_row):
        """Setup event controllers for row interactions"""
        # Double-click handling
        click_controller = Gtk.GestureClick.new()
        click_controller.set_button(1)  # Left mouse button
        click_controller.connect("pressed", self.on_row_clicked, list_item_or_row)
        row.add_controller(click_controller)

        # Right-click handling
        right_click_controller = Gtk.GestureClick.new()
        right_click_controller.set_button(3)  # Right mouse button
        right_click_controller.connect("pressed", self.on_row_right_click, row)
        row.add_controller(right_click_controller)

    def _bind_song_data_to_row(self, row: Adw.ActionRow, song: Song, position: int):
        """Bind song data to row elements"""
        # Set track number
        getattr(row, "number_label").set_text(f"{position + 1}")

        # Set song title and artist using ActionRow properties
        title = song.get_title()
        artist = song.artist
        album = song.album

        row.set_title(GLib.markup_escape_text(title))
        row.set_subtitle(GLib.markup_escape_text(f"{artist} - {album}"))

        # Load album art lazily only if not already loaded
        album_art_widget = getattr(row, "album_art")
        # Check if we already have album art for this song
        if not hasattr(album_art_widget, "loaded_song_file") or getattr(album_art_widget, "loaded_song_file") != song.file:
            # Try to load album art asynchronously
            AsyncUIHelper.run_async_operation(
                self._load_song_art,
                lambda result, widget=album_art_widget, file=song.file: self._update_item_art(widget, result, file),
                song,
                task_priority=110,  # Lower priority for album art loading
            )

        # Check if this is the current song
        if (
            self.mpd_client.is_connected()
            and self.mpd_client.current_song
            and self.mpd_client.current_song.get("id") == song.id
        ):
            getattr(row, "playing_icon").set_opacity(1)
        else:
            getattr(row, "playing_icon").set_opacity(0)

    def _update_item_art(self, album_art_widget: Gtk.Image, pixbuf, song_file: str):
        """Update album art widget with new pixbuf"""
        if pixbuf:
            album_art_widget.set_from_pixbuf(pixbuf)
            setattr(album_art_widget, "pixbuf_data", pixbuf)
        else:
            album_art_widget.set_from_icon_name("audio-x-generic-symbolic")
            setattr(album_art_widget, "pixbuf_data", None)
        # Mark this widget as having loaded art for this song
        setattr(album_art_widget, "loaded_song_file", song_file)

    async def _load_song_art(self, song: Song):
        """Load album art for a specific song"""
        return await get_album_art_as_pixbuf(
            self.mpd_client, song.file, 200
        )

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
        """Handle song change - update the playing indicator only"""
        self._update_playing_indicator()

    def _update_playing_indicator(self):
        """Update playing indicator for all rows without full refresh"""
        if not self.mpd_client.is_connected():
            return

        current_song_id = None
        if self.mpd_client.current_song:
            current_song_id = self.mpd_client.current_song.get("id")

        # Update all rows
        row = self.playlist_view.get_first_child()
        while row:
            if hasattr(row, "song") and hasattr(row, "playing_icon"):
                song = getattr(row, "song")
                playing_icon = getattr(row, "playing_icon")
                if current_song_id and song.id == current_song_id:
                    if playing_icon.get_opacity() == 0:
                        playing_icon.set_opacity(1)
                else:
                    if playing_icon.get_opacity() == 1:
                        playing_icon.set_opacity(0)
            row = row.get_next_sibling()

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
        idle_add_once(self._update_playlist_ui, new_playlist, current_song_id)
        return False

    def _update_playlist_ui(
        self, new_playlist: list[Song], current_song_id: int | None
    ):
        """Update the playlist UI with new data - runs in main thread"""

        # Create dictionary of existing rows by their song ID
        existing_rows = {}
        row = self.playlist_view.get_first_child()
        while row:
            if (
                getattr(row, "song", False)
                and getattr(getattr(row, "song"), "id", None) is not None
            ):
                existing_rows[getattr(row, "song").id] = row
            row = row.get_next_sibling()

        # Build a new list of song IDs from the playlist
        new_song_ids = [song.id for song in new_playlist]

        # Remove rows that are no longer in the playlist
        row = self.playlist_view.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            if (
                getattr(row, "song", False)
                and getattr(getattr(row, "song"), "id", None) not in new_song_ids
            ):
                self.playlist_view.remove(row)
            row = next_row

        # Update or add rows in the correct positions
        for i, song in enumerate(new_playlist):
            if song.id in existing_rows:
                # Update existing row
                row = existing_rows[song.id]
                setattr(row, "position", i)
                getattr(row, "number_label").set_text(f"{i + 1}")

                # Reset play indicator (will set it if it's the current song)
                getattr(row, "playing_icon").set_opacity(0)

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
                row = self.create_playlist_row(song, i)
                self.playlist_view.insert(row, i)

            # Update the current playing song indicator
            if current_song_id and song.id == current_song_id:
                getattr(row, "playing_icon").set_opacity(1)

        # Update status bar
        total_time = sum(float(getattr(song, "time", 0)) for song in new_playlist)
        song_count = len(new_playlist)
        self.status_label.set_text(
            f"{song_count} {'song' if song_count == 1 else 'songs'}, "
            f"{self.format_time(total_time)} total time"
        )

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
            transient_for=self.get_root(),  # pyright: ignore[reportArgumentType]
            title="Save Playlist",
            body="Enter a name for the playlist:",
        )

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        entry = Adw.EntryRow()
        entry.set_title("Playlist Name")
        entry.set_margin_top(12)

        # Create a preferences group to contain the entry
        group = Adw.PreferencesGroup()
        group.add(entry)

        dialog.set_extra_child(group)

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
        selected_positions = [getattr(r, "position") for r in selected_rows]

        # Determine the last selected row for play action
        last_selected_position = (
            selected_positions[-1]
            if len(selected_positions) > 0
            else getattr(row, "position", None)
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
            start_pos = getattr(self.last_selected_row, "position")
            end_pos = getattr(row, "position")

            # Ensure start is before end
            if start_pos > end_pos:
                start_pos, end_pos = end_pos, start_pos

            # Select all rows in the range
            current_row = self.playlist_view.get_first_child()

            pos = 0
            while current_row:
                if start_pos <= pos <= end_pos:
                    if isinstance(current_row, Gtk.ListBoxRow):
                        self.playlist_view.select_row(current_row)
                pos += 1
                current_row = current_row.get_next_sibling()

        elif ctrl_pressed:
            # Toggle selection with Ctrl
            if row in self.playlist_view.get_selected_rows():
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
        # Use Adwaita ActionRow for better integration
        row = Adw.ActionRow()
        setattr(row, "song", song)
        setattr(row, "position", position)
        row.set_activatable(True)

        # Create the common row elements
        self._setup_row_elements(row)

        # Set song data
        self._bind_song_data_to_row(row, song, position)

        # Setup event controllers for standalone row
        self._setup_row_controllers(row, row)

        return row

    def on_playlist_item_activated(self, listbox, row):
        """Handle playlist item activation"""
        if self.mpd_client.is_connected():
            position = row.position
            AsyncUIHelper.run_async_operation(
                self.mpd_client.async_play, None, position
            )

    def _play_selected_item(self, position):
        """Play the selected item in the playlist"""
        if self.mpd_client.is_connected() and position is not None:
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
        adj = scrolled_window.get_vadjustment()  # type: ignore
        if not adj:
            return

        # Get the allocation rectangle for the row
        rect = row.get_allocation()
        if not rect:
            return

        # Calculate start and target positions
        start_value = adj.get_value()
        target_value = rect.y

        # Cancel any ongoing scroll animation
        if hasattr(self, "_scroll_animation_id") and self._scroll_animation_id:
            GLib.source_remove(self._scroll_animation_id)
            self._scroll_animation_id = None

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
            self._scroll_animation_id = None
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
            self._scroll_animation_id = GLib.timeout_add(
                int(1000 / 60),
                self._animate_scroll,
                adj,
                start_value,
                target_value,
                total_frames,
                current_frame + 1,
            )
        else:
            self._scroll_animation_id = None

        return False  # Remove from idle sources
