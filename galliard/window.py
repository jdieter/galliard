#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from galliard.widgets.header_bar import HeaderBar  # noqa: E402
from galliard.widgets.player_controls import PlayerControls  # noqa: E402
from galliard.widgets.playlist_view import PlaylistView  # noqa: E402
from galliard.widgets.library_view import LibraryView  # noqa: E402
from galliard.widgets.now_playing import NowPlayingView  # noqa: E402


class MainWindow(Gtk.ApplicationWindow):
    """Main window for the Galliard application"""

    def __init__(self, application, mpd_client):
        super().__init__(application=application)

        # Store mpd client and application
        self.mpd_client = mpd_client
        self.application = application
        self.config = application.config

        # Set up window properties
        self.set_title("Galliard")
        self.set_default_size(900, 600)
        self.set_size_request(600, 400)

        # Setup proper window decorations
        self.set_titlebar(None)
        self.set_decorated(False)
        self.add_css_class("rounded")  # Add rounded class for curved window borders
        self.add_css_class("csd")  # Client-side decoration for proper GNOME styling
        self.add_css_class("shadow")  # Add shadow class for the standard drop shadow

        # Create window content
        self.create_ui()

        # Connect signals
        self.connect_signals()

        # Setup keyboard shortcuts
        self.setup_keyboard_shortcuts()

        # Handle close request for system tray minimization
        self.connect("close-request", self.on_close_request)

    def create_ui(self):
        """Create the user interface"""
        # Create main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)

        # Create header bar and make it draggable to move window
        self.header_bar = HeaderBar(self.mpd_client)
        self.main_box.append(self.header_bar)

        # Create player controls at the top, just below header
        self.player_controls = PlayerControls(self.mpd_client)
        self.main_box.append(self.player_controls)

        # Create main split pane that divides sidebar from content
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_paned.set_vexpand(True)
        self.main_paned.set_hexpand(True)
        self.main_box.append(self.main_paned)

        # Create sidebar for navigation
        self.create_sidebar()
        self.main_paned.set_start_child(self.sidebar)

        # Create stack to hold the different views/panes
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.content_stack.set_transition_duration(200)
        self.content_stack.set_vexpand(True)
        self.content_stack.set_hexpand(True)
        self.main_paned.set_end_child(self.content_stack)

        # Create library view
        self.library_view = LibraryView(self.mpd_client)
        self.content_stack.add_titled(self.library_view, "library", "Library")

        # Create playlist view
        self.playlist_view = PlaylistView(self.mpd_client)
        self.content_stack.add_titled(self.playlist_view, "playlists", "Playlists")

        # Create now playing view
        self.now_playing = NowPlayingView(self.mpd_client)
        self.content_stack.add_titled(self.now_playing, "now_playing", "Now Playing")

        # Set reasonable position for the paned division (sidebar width)
        self.main_paned.set_position(200)

        # Connect sidebar selection signal now that content_stack exists
        self.sidebar_list.connect("row-selected", self.on_sidebar_item_selected)

        # Select first item by default
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))

    def create_sidebar(self):
        """Create sidebar navigation"""
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.add_css_class("sidebar")
        self.sidebar.set_size_request(180, -1)  # Minimum width for sidebar

        # Create sidebar list
        self.sidebar_list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
        )
        self.sidebar_list.add_css_class("navigation-sidebar")
        self.sidebar_list.set_vexpand(True)
        self.sidebar.append(self.sidebar_list)

        # Create sidebar items
        self.add_sidebar_item("Library", "media-optical-symbolic", "library")
        self.add_sidebar_item("Playlists", "view-list-symbolic", "playlists")
        self.add_sidebar_item("Now Playing", "audio-x-generic-symbolic", "now_playing")

    def add_sidebar_item(self, label_text, icon_name, page_name):
        """Add an item to the sidebar"""
        # Replace Adw.ActionRow with custom implementation using Gtk.Box
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        box.append(icon)

        label = Gtk.Label(label=label_text, xalign=0)
        label.set_hexpand(True)
        box.append(label)

        row = Gtk.ListBoxRow(child=box)
        row.page_name = page_name

        self.sidebar_list.append(row)

    def on_sidebar_item_selected(self, list_box, row):
        """Handle sidebar item selection"""
        if row is None:
            return

        page_name = row.page_name
        self.content_stack.set_visible_child_name(page_name)

    def connect_signals(self):
        """Connect signals"""
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("connection-error", self.on_mpd_connection_error)

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        GLib.idle_add(self.player_controls.clear_connection_error)
        GLib.idle_add(self.player_controls.update_controls_sensitivity, True)

    def on_mpd_connection_error(self, client, message):
        """Handle MPD connection error"""
        # Show the error in player controls instead of displaying a dialog
        GLib.idle_add(self.player_controls.show_connection_error, message)

    def setup_keyboard_shortcuts(self):
        """Set up keyboard shortcuts"""
        # Media key actions
        actions = [
            ("play-pause", self.on_play_pause, None),
            ("next", self.on_next, None),
            ("previous", self.on_previous, None),
            ("stop", self.on_stop, None),
        ]

        # Create action group
        action_group = Gio.SimpleActionGroup()

        # Add actions to group
        for name, callback, param_type in actions:
            action = Gio.SimpleAction.new(name, param_type)
            action.connect("activate", callback)
            action_group.add_action(action)

        # Insert the action group
        self.insert_action_group("win", action_group)

        # Set keyboard shortcuts
        app = self.get_application()
        app.set_accels_for_action("win.play-pause", ["space"])
        app.set_accels_for_action("win.next", ["<primary>Right"])
        app.set_accels_for_action("win.previous", ["<primary>Left"])
        app.set_accels_for_action("win.stop", ["<primary>s"])

    def on_play_pause(self, action, param):
        """Toggle play/pause"""
        if not self.mpd_client.is_connected():
            return

        status = self.mpd_client.status
        if status.get("state") == "play":
            self.mpd_client.pause()
        else:
            self.mpd_client.play()

    def on_next(self, action, param):
        """Play next track"""
        if self.mpd_client.is_connected():
            self.mpd_client.next()

    def on_previous(self, action, param):
        """Play previous track"""
        if self.mpd_client.is_connected():
            self.mpd_client.previous()

    def on_stop(self, action, param):
        """Stop playback"""
        if self.mpd_client.is_connected():
            self.mpd_client.stop()

    def on_close_request(self, window):
        """Handle window close request"""
        # If minimize to tray is enabled, hide window instead of closing
        if self.config.get("ui.minimize_to_tray", True):
            # Check if system tray is available
            # We can check this by seeing if the application has a system_tray_icon attribute
            if (
                hasattr(self.application, "system_tray_icon")
                and self.application.system_tray_icon
            ):
                self.set_visible(False)
                return True  # Prevent default close behavior

        # Default close behavior
        return False
