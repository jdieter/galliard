import gi
import logging

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, Adw  # noqa: E402


class HeaderBar(Gtk.Box):
    """The main window's header bar: connect button, search bar, app menu."""

    def __init__(self, mpd_conn, window):
        """Build the header chrome and subscribe to MPD connection events."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.mpd_conn = mpd_conn
        self.window = window

        self.header = Adw.HeaderBar()
        self.append(self.header)

        self.title_widget = self.create_title_widget()
        self.header.set_title_widget(self.title_widget)

        self.connect_button = Gtk.Button(
            icon_name="network-server-symbolic", tooltip_text="Connect to MPD server"
        )
        self.connect_button.connect("clicked", self.on_connect_clicked)
        self.header.pack_start(self.connect_button)

        self.search_button = Gtk.ToggleButton(
            icon_name="system-search-symbolic", tooltip_text="Search library"
        )
        self.search_button.connect("toggled", self.on_search_toggled)
        self.header.pack_start(self.search_button)

        self.search_bar = Gtk.SearchBar()
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.search_type_dropdown = Gtk.DropDown()

        # Map visible dropdown positions to MPD's search-type keywords.
        self.search_type_map = {
            0: "any",
            1: "title",
            2: "album",
            3: "artist",
            4: "date",
        }

        search_types = Gtk.StringList()
        search_types.append("Any")
        search_types.append("Song")
        search_types.append("Album")
        search_types.append("Artist")
        search_types.append("Year")
        self.search_type_dropdown.set_model(search_types)
        self.search_type_dropdown.set_selected(0)
        search_box.append(self.search_type_dropdown)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self.on_search_changed)

        # While the search entry has focus the space key should type a
        # literal space rather than trigger the global play/pause accelerator.
        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("enter", self.on_search_focus_in)
        focus_controller.connect("leave", self.on_search_focus_out)
        self.search_entry.add_controller(focus_controller)

        search_box.append(self.search_entry)

        self.search_bar.set_child(search_box)
        self.search_bar.connect_entry(self.search_entry)
        self.append(self.search_bar)

        self.menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic", tooltip_text="Main menu"
        )
        self.create_main_menu()
        self.header.pack_end(self.menu_button)

        self.mpd_conn.connect_signal(
            "connecting-blocked", self.on_mpd_connecting_blocked
        )
        self.mpd_conn.connect_signal("connecting", self.on_mpd_connecting)
        self.mpd_conn.connect_signal("connected", self.on_mpd_connected)
        self.mpd_conn.connect_signal(
            "disconnecting-blocked", self.on_mpd_disconnecting_blocked
        )
        self.mpd_conn.connect_signal("disconnected", self.on_mpd_disconnected)
        self.mpd_conn.connect_signal("song-changed", self.on_song_changed)

        self.current_subtitle = "Not connected"

    def create_title_widget(self):
        """Return the Adw.WindowTitle used as the header's centre widget."""
        self.window_title = Adw.WindowTitle(title="Galliard", subtitle="Not connected")
        return self.window_title

    def create_main_menu(self):
        """Build the hamburger-menu model with connection / prefs / quit sections."""
        menu = Gio.Menu()

        connection_section = Gio.Menu()
        connection_section.append("Connect", "app.connect")
        connection_section.append("Disconnect", "app.disconnect")
        menu.append_section(None, connection_section)

        prefs_section = Gio.Menu()
        prefs_section.append("Preferences", "app.preferences")
        prefs_section.append("About", "app.about")
        menu.append_section(None, prefs_section)

        quit_section = Gio.Menu()
        quit_section.append("Quit", "app.quit")
        menu.append_section(None, quit_section)

        self.menu_button.set_menu_model(menu)

    def update_connection_status(self, connected):
        """Reflect the MPD connection state in the title subtitle + connect button.

        ``connected`` is a small enum: 0 connecting-blocked, 1 connecting,
        2 connected, 3 disconnecting, anything else treated as disconnected.
        """
        print(f"Updating connection status: {connected}")
        if connected == 0:
            self.set_subtitle("Connecting...")
            self.connect_button.set_icon_name("network-wireless-acquiring-symbolic")
            self.connect_button.set_tooltip_text("Connecting to MPD server")
            self.connect_button.set_sensitive(False)
        elif connected == 1:
            self.set_subtitle("Connecting...")
            self.connect_button.set_icon_name("network-wireless-acquiring-symbolic")
            self.connect_button.set_tooltip_text("Connecting to MPD server")
            self.connect_button.set_sensitive(True)
        elif connected == 2:
            self.set_subtitle("Connected")
            self.connect_button.set_icon_name(
                "network-wireless-signal-excellent-symbolic"
            )
            self.connect_button.set_tooltip_text("Connected to MPD server")
            self.connect_button.set_sensitive(True)
        elif connected == 3:
            self.set_subtitle("Disconnecting...")
            self.connect_button.set_icon_name("network-server-symbolic")
            self.connect_button.set_tooltip_text("Disconnecting from MPD server")
            self.connect_button.set_sensitive(False)
        else:
            self.set_subtitle("Not connected")
            self.connect_button.set_icon_name("network-server-symbolic")
            self.connect_button.set_tooltip_text("Connect to MPD server")
            self.connect_button.set_sensitive(True)

    def set_subtitle(self, text):
        """Set the header subtitle, remembering it for later redisplay."""
        self.current_subtitle = text
        self.window_title.set_subtitle(text)

    def on_connect_clicked(self, button):
        """Toggle the MPD connection when the header's network button is clicked."""
        if not self.mpd_conn.is_connected():
            self.mpd_conn.connect_to_server()
        else:
            self.mpd_conn.disconnect_from_server()

    def on_mpd_connecting_blocked(self, client):
        """Signal handler: MPD connect is queued behind another operation."""
        print("MPD connecting blocked...")
        self.update_connection_status(0)

    def on_mpd_connecting(self, client):
        """Signal handler: MPD connection attempt in progress."""
        print("MPD connecting...")
        self.update_connection_status(1)

    def on_mpd_connected(self, client):
        """Signal handler: MPD connection established."""
        print("MPD connected")
        self.update_connection_status(2)

    def on_mpd_disconnecting_blocked(self, client):
        """Signal handler: MPD disconnect queued behind another operation."""
        print("MPD disconnecting blocked...")
        self.update_connection_status(3)

    def on_mpd_disconnected(self, client):
        """Signal handler: MPD connection closed."""
        print("MPD disconnected")
        self.update_connection_status(4)

    def on_song_changed(self, client):
        """Signal handler: update the subtitle with the new song's title/artist."""
        if self.mpd_conn.is_connected() and self.mpd_conn.current_song:
            song = self.mpd_conn.current_song
            title = song.get("title", "Unknown")
            artist = song.get("artist", "Unknown")
            self.set_subtitle(f"{title} - {artist}")

    def on_search_toggled(self, button):
        """Show or hide the search bar and focus the entry when shown."""
        self.search_bar.set_search_mode(button.get_active())
        if button.get_active():
            self.search_entry.grab_focus()

    def on_search_changed(self, entry):
        """Propagate search text + selected type to the registered callback."""
        query = entry.get_text()
        selected_index = self.search_type_dropdown.get_selected()
        search_type = self.search_type_map[selected_index]

        if hasattr(self, "search_changed_callback"):
            self.search_changed_callback(query, search_type)

    def on_search_focus_in(self, controller):
        """Disable the space-bar play/pause shortcut while typing in search."""
        logging.debug("Search entry focused in")
        self.window.remove_space_accel()

    def on_search_focus_out(self, controller):
        """Restore the space-bar play/pause shortcut when search loses focus."""
        logging.debug("Search entry focused out")
        self.window.restore_space_accel()

    def set_search_changed_callback(self, callback):
        """Register ``callback(query, search_type)`` fired on search input."""
        self.search_changed_callback = callback
