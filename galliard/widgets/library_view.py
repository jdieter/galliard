import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402
from galliard.widgets.files_view import FilesView  # noqa: E402
from galliard.widgets.artists_view import ArtistsView  # noqa: E402
from galliard.widgets.albums_view import AlbumsView  # noqa: E402


class LibraryView(Gtk.Box):
    """Library pane: a Files / Artists / Albums switcher over a Gtk.Stack."""

    def __init__(self, mpd_client):
        """Build the sub-views and watch for MPD connect/disconnect."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.mpd_client = mpd_client
        self.current_view = "files"

        self.create_ui()

        self.mpd_client.connect_signal("connected", self.on_mpd_connected)
        self.mpd_client.connect_signal("disconnected", self.on_mpd_disconnected)

    def create_ui(self):
        """Build the toolbar (view toggles + refresh) and the content stack."""
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_box.add_css_class("toolbar")
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)
        header_box.set_margin_top(6)
        header_box.set_margin_bottom(6)

        view_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        view_box.add_css_class("linked")

        self.files_button = Gtk.ToggleButton(label="Files", active=True)
        self.files_button.connect("toggled", self.on_view_toggled, "files")
        view_box.append(self.files_button)

        self.artists_button = Gtk.ToggleButton(label="Artists")
        self.artists_button.connect("toggled", self.on_view_toggled, "artists")
        view_box.append(self.artists_button)

        self.albums_button = Gtk.ToggleButton(label="Albums")
        self.albums_button.connect("toggled", self.on_view_toggled, "albums")
        view_box.append(self.albums_button)

        header_box.append(view_box)

        refresh_button = Gtk.Button(
            icon_name="view-refresh-symbolic", tooltip_text="Refresh library"
        )
        refresh_button.set_margin_start(6)
        refresh_button.connect("clicked", self.on_refresh_clicked)
        header_box.append(refresh_button)

        self.append(header_box)

        self.content_stack = Gtk.Stack()
        self.content_stack.set_vexpand(True)

        self.files_view = FilesView(self.mpd_client)
        self.artists_view = ArtistsView(self.mpd_client)
        self.albums_view = AlbumsView(self.mpd_client)

        self.content_stack.add_named(self.files_view, "files")
        self.content_stack.add_named(self.artists_view, "artists")
        self.content_stack.add_named(self.albums_view, "albums")

        self.content_stack.set_visible_child_name("files")

        self.append(self.content_stack)

    def on_view_toggled(self, button, view_name):
        """Swap the stack to the selected view and deactivate the other toggles."""
        if button.get_active():
            self.content_stack.set_visible_child_name(view_name)
            self.current_view = view_name
            AsyncUIHelper.run_async_operation(self.refresh_library, None)

            # ToggleButtons don't implement radio behaviour on their own.
            for btn, name in [
                (self.files_button, "files"),
                (self.artists_button, "artists"),
                (self.albums_button, "albums"),
            ]:
                if name != view_name and btn.get_active():
                    btn.set_active(False)

    def on_refresh_clicked(self, button):
        """Toolbar refresh button: reload the current library view."""
        AsyncUIHelper.run_async_operation(self.refresh_library, None)

    def on_mpd_connected(self, client):
        """On reconnect, reload the current view to pick up library changes."""
        AsyncUIHelper.run_async_operation(self.refresh_library, None)

    def on_mpd_disconnected(self, client):
        """No-op: the sub-views manage their own empty-state."""
        pass

    async def refresh_library(self):
        """Ask the currently-visible sub-view to reload from MPD."""
        if not self.mpd_client.is_connected():
            return

        if self.current_view == "files":
            self.files_view.refresh()
        elif self.current_view == "artists":
            self.artists_view.refresh()
        elif self.current_view == "albums":
            self.albums_view.refresh()
