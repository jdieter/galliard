import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402
from galliard.widgets.files_view import FilesView  # noqa: E402
from galliard.widgets.artists_view import ArtistsView  # noqa: E402
from galliard.widgets.albums_view import AlbumsView  # noqa: E402


class LibraryView(Gtk.Box):
    """Library view widget for Galliard"""

    def __init__(self, mpd_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.mpd_client = mpd_client
        self.current_view = "files"  # files, artists, albums

        # Create UI
        self.create_ui()

        # Connect signals
        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)

    def create_ui(self):
        """Create the user interface"""
        # Create header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_box.add_css_class("toolbar")
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)
        header_box.set_margin_top(6)
        header_box.set_margin_bottom(6)

        # View switcher
        view_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        view_box.add_css_class("linked")

        # Files button
        self.files_button = Gtk.ToggleButton(
            label="Files", active=True  # Start with files view active
        )
        self.files_button.connect("toggled", self.on_view_toggled, "files")
        view_box.append(self.files_button)

        # Artists button
        self.artists_button = Gtk.ToggleButton(label="Artists")
        self.artists_button.connect("toggled", self.on_view_toggled, "artists")
        view_box.append(self.artists_button)

        # Albums button
        self.albums_button = Gtk.ToggleButton(label="Albums")
        self.albums_button.connect("toggled", self.on_view_toggled, "albums")
        view_box.append(self.albums_button)

        header_box.append(view_box)

        # Add refresh button
        refresh_button = Gtk.Button(
            icon_name="view-refresh-symbolic", tooltip_text="Refresh library"
        )
        refresh_button.set_margin_start(6)
        refresh_button.connect("clicked", self.on_refresh_clicked)
        header_box.append(refresh_button)

        self.append(header_box)

        # Create main content
        self.content_stack = Gtk.Stack()
        self.content_stack.set_vexpand(True)

        # Create the view components
        self.files_view = FilesView(self.mpd_client)
        self.artists_view = ArtistsView(self.mpd_client)
        self.albums_view = AlbumsView(self.mpd_client)

        # Add views to the stack
        self.content_stack.add_named(self.files_view, "files")
        self.content_stack.add_named(self.artists_view, "artists")
        self.content_stack.add_named(self.albums_view, "albums")

        # Set initial view
        self.content_stack.set_visible_child_name("files")

        self.append(self.content_stack)

    def on_view_toggled(self, button, view_name):
        """Handle view toggle button"""
        if button.get_active():
            self.content_stack.set_visible_child_name(view_name)
            self.current_view = view_name
            AsyncUIHelper.run_async_operation(
                self.refresh_library, None  # No callback needed
            )

            # Ensure only one toggle button is active
            for btn, name in [
                (self.files_button, "files"),
                (self.artists_button, "artists"),
                (self.albums_button, "albums"),
            ]:
                if name != view_name and btn.get_active():
                    btn.set_active(False)

    def on_refresh_clicked(self, button):
        """Handle refresh button click"""
        AsyncUIHelper.run_async_operation(
            self.refresh_library, None  # No callback needed
        )

    def on_mpd_connected(self, client):
        """Handle MPD connection"""
        AsyncUIHelper.run_async_operation(
            self.refresh_library, None  # No callback needed
        )

    def on_mpd_disconnected(self, client):
        """Handle MPD disconnection"""
        # Nothing to do, each view handles its own state
        pass

    async def refresh_library(self):
        """Refresh the current view"""
        if not self.mpd_client.is_connected():
            return

        # Refresh current view
        if self.current_view == "files":
            self.files_view.refresh()
        elif self.current_view == "artists":
            self.artists_view.refresh()
        elif self.current_view == "albums":
            self.albums_view.refresh()
