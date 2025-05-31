import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GLib, Adw  # noqa: E402


class HeaderBar(Gtk.Box):
    """Header bar widget for Galliard"""

    def __init__(self, mpd_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.mpd_client = mpd_client

        # Create the header bar using Adw
        self.header = Adw.HeaderBar()
        self.append(self.header)

        # Set window title
        self.title_widget = self.create_title_widget()
        self.header.set_title_widget(self.title_widget)

        # Connect button
        self.connect_button = Gtk.Button(
            icon_name="network-server-symbolic", tooltip_text="Connect to MPD server"
        )
        self.connect_button.connect("clicked", self.on_connect_clicked)
        self.header.pack_start(self.connect_button)

        # Search button
        self.search_button = Gtk.ToggleButton(
            icon_name="system-search-symbolic", tooltip_text="Search library"
        )
        self.search_button.connect("toggled", self.on_search_toggled)
        self.header.pack_start(self.search_button)

        # Search bar
        self.search_bar = Gtk.SearchBar()
        self.search_entry = Gtk.SearchEntry()
        self.search_bar.set_child(self.search_entry)
        self.search_bar.connect_entry(self.search_entry)
        self.append(self.search_bar)

        # Menu button
        self.menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic", tooltip_text="Main menu"
        )
        self.create_main_menu()
        self.header.pack_end(self.menu_button)

        # Connect signals
        self.mpd_client.connect_signal(
            "connecting-blocked", self.on_mpd_connecting_blocked
        )
        self.mpd_client.connect_signal("connecting", self.on_mpd_connecting)
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal(
            "disconnecting-blocked", self.on_mpd_disconnecting_blocked
        )
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)
        self.mpd_client.connect_signal("song-changed", self.on_song_changed)

        # Store current subtitle for title updates
        self.current_subtitle = "Not connected"

    def create_title_widget(self):
        """Create a custom title widget using Adw.WindowTitle"""
        self.window_title = Adw.WindowTitle(title="Galliard", subtitle="Not connected")
        return self.window_title

    def create_main_menu(self):
        """Create the main menu"""
        # Create menu model
        menu = Gio.Menu()

        # Add connection section
        connection_section = Gio.Menu()
        connection_section.append("Connect", "app.connect")
        connection_section.append("Disconnect", "app.disconnect")
        menu.append_section(None, connection_section)

        # Add preferences and about section
        prefs_section = Gio.Menu()
        prefs_section.append("Preferences", "app.preferences")
        prefs_section.append("About", "app.about")
        menu.append_section(None, prefs_section)

        # Add quit section
        quit_section = Gio.Menu()
        quit_section.append("Quit", "app.quit")
        menu.append_section(None, quit_section)

        # Connect menu to button
        self.menu_button.set_menu_model(menu)

    def update_connection_status(self, connected):
        """Update UI to reflect connection status"""
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
        """Update the subtitle text"""
        self.current_subtitle = text
        self.window_title.set_subtitle(text)

    def on_connect_clicked(self, button):
        """Handle connect button click"""
        if not self.mpd_client.is_connected():
            self.mpd_client.connect()
        else:
            self.mpd_client.disconnect()

    def on_mpd_connecting_blocked(self, client):
        """Handle MPD connecting blocked"""
        print("MPD connecting blocked...")
        GLib.idle_add(self.update_connection_status, 0)

    def on_mpd_connecting(self, client):
        """Handle MPD connection"""
        print("MPD connecting...")
        GLib.idle_add(self.update_connection_status, 1)

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        print("MPD connected")
        GLib.idle_add(self.update_connection_status, 2)

    def on_mpd_disconnecting_blocked(self, client):
        """Handle MPD disconnection blocked"""
        print("MPD disconnecting blocked...")
        GLib.idle_add(self.update_connection_status, 3)

    def on_mpd_disconnected(self, client):
        """Handle MPD disconnection"""
        print("MPD disconnected")
        GLib.idle_add(self.update_connection_status, 4)

    def on_song_changed(self, client):
        """Handle song change"""
        if self.mpd_client.is_connected() and self.mpd_client.current_song:
            song = self.mpd_client.current_song
            title = song.get("title", "Unknown")
            artist = song.get("artist", "Unknown")
            GLib.idle_add(self.set_subtitle, f"{title} - {artist}")

    def on_search_toggled(self, button):
        """Handle search button toggle"""
        self.search_bar.set_search_mode(button.get_active())

    def setup_search_entry(self, window):
        """Set up search entry after window is created"""
        self.search_bar.set_key_capture_widget(window)
