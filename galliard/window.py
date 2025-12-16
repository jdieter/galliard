#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GLib, Adw  # noqa: E402

from galliard.widgets.header_bar import HeaderBar  # noqa: E402
from galliard.widgets.player_controls import PlayerControls  # noqa: E402
from galliard.widgets.playlist_view import PlaylistView  # noqa: E402
from galliard.widgets.library_view import LibraryView  # noqa: E402
from galliard.widgets.now_playing import NowPlayingView  # noqa: E402
from galliard.widgets.search_results_view import SearchResultsView  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    """Main window for the Galliard application"""

    def __init__(self, application, mpd_conn):
        super().__init__(application=application)

        self.mpd_conn = mpd_conn
        self.application = application
        self.config = application.config

        # Window setup
        self.set_title("Galliard")
        self.set_default_size(900, 600)
        self.set_size_request(600, 400)
        self.pages = {}
        self.create_ui()
        self.setup_keyboard_shortcuts()

        # Connect signals
        mpd_conn.connect_signal("connected", self.on_mpd_connected)
        mpd_conn.connect_signal("connection-error", self.on_mpd_connection_error)
        self.connect("close-request", self.on_close_request)

    def create_ui(self):
        """Create the user interface"""
        # Main layout
        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        # Header and controls
        self.header_bar = HeaderBar(self.mpd_conn)
        self.player_controls = PlayerControls(self.mpd_conn)
        self.toolbar_view.add_top_bar(self.header_bar)
        self.toolbar_view.add_top_bar(self.player_controls)

        # Split view
        self.navigation_split_view = Adw.NavigationSplitView()
        self.navigation_split_view.set_sidebar_width_fraction(0.25)
        self.navigation_split_view.set_min_sidebar_width(200)
        self.navigation_split_view.set_max_sidebar_width(300)
        self.navigation_split_view.set_show_content(True)
        self.toolbar_view.set_content(self.navigation_split_view)

        # Create sidebar and content
        self.create_sidebar()
        self.create_content()

        # Connect search callback
        def on_search_changed(query, search_type):
            if query.strip():
                # Show search results page
                visible_page = self.content_navigation.get_visible_page()
                if visible_page and visible_page.get_tag() != "search":
                    self.page_before_search = visible_page.get_tag()
                    self.content_navigation.replace([self.pages["search"]])

                # Hide sidebar and player controls
                self.navigation_split_view.set_collapsed(True)
                self.player_controls.set_visible(False)

                # Perform search
                AsyncUIHelper.run_async_operation(
                    self.search_results_view.perform_search,
                    None,
                    query,
                )
            else:
                # Return to previous page when search is cleared
                visible_page = self.content_navigation.get_visible_page()
                if visible_page and visible_page.get_tag() == "search":
                    self.content_navigation.replace([self.pages[self.page_before_search]])

                    # Show sidebar and player controls
                    self.navigation_split_view.set_collapsed(False)
                    self.player_controls.set_visible(True)

        self.header_bar.set_search_changed_callback(on_search_changed)

        # Connect to search bar toggle
        self.header_bar.search_button.connect("toggled", self.on_search_toggled)

    def on_search_toggled(self, button):
        """Handle search toggle - return to previous page when closing"""
        if not button.get_active():
            visible_page = self.content_navigation.get_visible_page()
            if visible_page and visible_page.get_tag() == "search":
                self.content_navigation.replace([self.pages[self.page_before_search]])

                # Show sidebar and player controls
                self.navigation_split_view.set_collapsed(False)
                self.player_controls.set_visible(True)

    def create_sidebar(self):
        """Create sidebar navigation"""
        sidebar_page = Adw.NavigationPage()
        sidebar_page.set_title("Navigation")

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_page.set_child(sidebar_box)

        self.sidebar_list = Gtk.ListBox()
        self.sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar_list.add_css_class("navigation-sidebar")
        self.sidebar_list.connect("row-selected", self.on_sidebar_item_selected)
        sidebar_box.append(self.sidebar_list)

        # Add navigation items
        items = [
            ("Library", "media-optical-symbolic", "library"),
            ("Playlists", "view-list-symbolic", "playlists"),
            ("Now Playing", "audio-x-generic-symbolic", "now_playing"),
        ]

        for title, icon, page_name in items:
            row = Adw.ActionRow()
            row.set_title(title)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            setattr(row, "page_name", page_name)
            self.sidebar_list.append(row)

        self.navigation_split_view.set_sidebar(sidebar_page)
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))

    def create_content(self):
        """Create main content area"""
        self.content_navigation = Adw.NavigationView()

        content_page = Adw.NavigationPage()
        content_page.set_child(self.content_navigation)
        self.navigation_split_view.set_content(content_page)

        # Create pages
        self.pages = {
            "library": self.create_page(
                "Library", "library", LibraryView(self.mpd_conn)
            ),
            "playlists": self.create_page(
                "Playlists", "playlists", PlaylistView(self.mpd_conn)
            ),
            "now_playing": self.create_page(
                "Now Playing", "now_playing", NowPlayingView(self.mpd_conn)
            ),
            "search": self.create_page(
                "Search Results", "search", SearchResultsView(self.mpd_conn)
            ),
        }

        # Store views for easy access
        self.library_view = self.pages["library"].get_child()
        self.playlist_view = self.pages["playlists"].get_child()
        self.now_playing = self.pages["now_playing"].get_child()
        self.search_results_view = self.pages["search"].get_child()

        # Add initial page
        self.content_navigation.add(self.pages["library"])

        # Track the page before search
        self.page_before_search = "library"

    def create_page(self, title, tag, child):
        """Helper to create navigation pages"""
        page = Adw.NavigationPage()
        page.set_title(title)
        page.set_tag(tag)
        page.set_child(child)
        return page

    def on_sidebar_item_selected(self, list_box, row):
        """Handle sidebar item selection"""
        if not row:
            return

        page_name = row.page_name
        if page_name in self.pages:
            visible_page = self.content_navigation.get_visible_page()
            if not visible_page or visible_page.get_tag() != page_name:
                self.content_navigation.replace([self.pages[page_name]])

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        GLib.idle_add(self.player_controls.clear_connection_error)
        GLib.idle_add(self.player_controls.update_controls_sensitivity, True)

    def on_mpd_connection_error(self, client, message):
        """Handle MPD connection error"""
        GLib.idle_add(self.player_controls.show_connection_error, message)

    def setup_keyboard_shortcuts(self):
        """Set up keyboard shortcuts"""
        shortcuts = [
            ("play-pause", self.on_play_pause, ["space"]),
            ("next", self.on_next, ["<primary>Right"]),
            ("previous", self.on_previous, ["<primary>Left"]),
            ("stop", self.on_stop, ["<primary>s"]),
        ]

        action_group = Gio.SimpleActionGroup()
        app = self.get_application()

        for name, callback, accels in shortcuts:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            action_group.add_action(action)
            if app:
                app.set_accels_for_action(f"win.{name}", accels)

        self.insert_action_group("win", action_group)

    def on_play_pause(self, action, param):
        """Toggle play/pause"""
        if self.mpd_conn.is_connected():
            status = self.mpd_conn.status
            if status.get("state") == "play":
                self.mpd_conn.pause()
            else:
                self.mpd_conn.play()

    def on_next(self, action, param):
        """Play next track"""
        if self.mpd_conn.is_connected():
            self.mpd_conn.next()

    def on_previous(self, action, param):
        """Play previous track"""
        if self.mpd_conn.is_connected():
            self.mpd_conn.previous()

    def on_stop(self, action, param):
        """Stop playback"""
        if self.mpd_conn.is_connected():
            self.mpd_conn.stop()

    def on_close_request(self, window):
        """Handle window close request"""
        if (
            self.config.get("ui.minimize_to_tray", True)
            and hasattr(self.application, "system_tray_icon")
            and self.application.system_tray_icon
        ):
            self.set_visible(False)
            return True
        return False
