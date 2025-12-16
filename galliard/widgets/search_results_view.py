import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from galliard.models import FileItem  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402


class SearchResultsView(Gtk.ScrolledWindow):
    """Search results view with hierarchical organization"""

    def __init__(self, mpd_conn):
        super().__init__()
        self.mpd_conn = mpd_conn

        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Create UI elements
        self.create_ui()

    def create_ui(self):
        """Create the search results UI"""
        # Create a list store for search results
        self.results_store = Gio.ListStore.new(FileItem)

        # Create tree list model
        self.tree_model = Gtk.TreeListModel.new(
            self.results_store,
            False,  # Passthrough
            False,  # Don't auto-expand
            self._create_children_model,
        )

        # Create selection model
        self.selection = Gtk.SingleSelection.new(self.tree_model)

        # Create column view
        self.results_tree = Gtk.ColumnView.new(self.selection)
        self.results_tree.set_show_column_separators(False)
        self.results_tree.set_show_row_separators(False)

        # Create factory for items
        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._item_setup)
        factory.connect("bind", self._item_bind)
        factory.connect("unbind", self._item_unbind)

        # Create column
        column = Gtk.ColumnViewColumn.new("Search Results", factory)
        column.set_expand(True)
        self.results_tree.append_column(column)

        # Hide the table header
        table_header = self.results_tree.get_first_child()
        if table_header:
            table_header.set_visible(False)

        # Connect selection signal
        self.selection.connect("selection-changed", self._on_selection_changed)

        # Add to scrolled window
        self.set_child(self.results_tree)

    def _item_setup(self, factory, list_item):
        """Setup function for items"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # Expander for categories
        expander = Gtk.Button.new_from_icon_name("pan-end-symbolic")
        expander.add_css_class("flat")
        expander.set_visible(False)
        box.append(expander)

        # Icon/album art
        image = Gtk.Image()
        image.set_size_request(20, 20)
        box.append(image)

        # Label
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        box.append(label)

        list_item.set_child(box)
        list_item.image = image
        list_item.label = label
        list_item.expander = expander

        expander.connect("clicked", self._on_expander_clicked, list_item)

    def _item_bind(self, factory, list_item):
        """Bind item data to widgets"""
        tree_list_row = list_item.get_item()
        file_item = tree_list_row.get_item()

        if not file_item:
            return

        # Calculate indentation
        depth = tree_list_row.get_depth()
        indent_pixels = depth * 24

        if file_item.is_directory:
            list_item.expander.set_margin_start(indent_pixels)
            list_item.expander.set_visible(True)

            is_expanded = tree_list_row.get_expanded()
            icon_name = "pan-down-symbolic" if is_expanded else "pan-end-symbolic"
            list_item.expander.set_icon_name(icon_name)
            list_item.image.set_margin_start(0)
        else:
            list_item.expander.set_visible(False)
            list_item.image.set_margin_start(indent_pixels + 26)

        # Set icon or pixbuf
        if file_item.pixbuf:
            list_item.image.set_from_pixbuf(file_item.pixbuf)
        else:
            list_item.image.set_from_icon_name(file_item.icon_name)

        list_item.label.set_text(file_item.name)
        list_item.tree_list_row = tree_list_row
        file_item.list_item = list_item

    def _item_unbind(self, factory, list_item):
        """Clean up when item is unbound"""
        list_item.tree_list_row = None

    def _create_children_model(self, file_item):
        """Create model for child items"""
        if not file_item.is_directory:
            return None

        child_store = Gio.ListStore.new(FileItem)

        if not file_item.children_loaded:
            # Children are already populated during search
            for child in file_item.children:
                child_store.append(child)
            file_item.children_loaded = True
        else:
            for child in file_item.children:
                child_store.append(child)

        return child_store

    def _on_expander_clicked(self, button, list_item):
        """Handle expander button click"""
        tree_list_row = list_item.tree_list_row
        if tree_list_row:
            is_expanded = tree_list_row.get_expanded()
            tree_list_row.set_expanded(not is_expanded)
            icon_name = "pan-end-symbolic" if is_expanded else "pan-down-symbolic"
            button.set_icon_name(icon_name)

    def _on_selection_changed(self, selection, position, n_items):
        """Handle selection"""
        selected = selection.get_selected_item()
        if not selected:
            return

        file_item = selected.get_item()
        if not file_item or file_item.is_directory:
            return

        # Play the selected song
        self.mpd_conn.add_to_playlist(file_item.path)
        playlist = self.mpd_conn.get_current_playlist()
        if playlist:
            self.mpd_conn.client.play(len(playlist) - 1)

    async def perform_search(self, query: str):
        for type in ["artist", "album", "title", "date"]:
            await self._perform_search(query, type)

    async def _perform_search(self, query: str, type: str):
        """Perform search and organize results"""
        if not query.strip():
            self.results_store.remove_all()
            return

        try:
            # Perform MPD search
            results = await self.mpd_conn.async_search(type, query)

            # Organize results into categories
            years = {}
            artists = {}
            albums = {}
            songs = []

            for item in results:
                # Categorize by year
                if type == "date":
                    year = item["date"]
                    if year not in years:
                        years[year] = []
                    years[year].append(item)

                # Categorize by artist
                artist = item.get("albumartist", item.get("artist", "Unknown"))
                if artist not in artists:
                    artists[artist] = []
                artists[artist].append(item)

                # Categorize by album
                album = item.get("album", "Unknown")
                if album not in albums:
                    albums[album] = []
                albums[album].append(item)

                # All items are songs
                songs.append(item)

            # Build result tree
            GLib.idle_add(self._build_results_tree, years, artists, albums, songs)

        except Exception as e:
            print(f"Error performing search: {e}")

    def _build_results_tree(self, years, artists, albums, songs):
        """Build the hierarchical results tree"""
        self.results_store.remove_all()

        # Years category
        if years:
            years_item = FileItem(
                name=f"Years ({len(years)})",
                path="",
                icon_name="x-office-calendar-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            years_item.children = []
            for year in sorted(years.keys(), reverse=True):
                year_item = FileItem(
                    name=f"{year} ({len(years[year])} songs)",
                    path="",
                    icon_name="folder-symbolic",
                    is_directory=True,
                    pixbuf=None,
                )
                year_item.children = [
                    FileItem(
                        name=f"{song.get('title', 'Unknown')} - {song.get('artist', 'Unknown')}",
                        path=song["file"],
                        icon_name="audio-x-generic-symbolic",
                        is_directory=False,
                        pixbuf=None,
                    )
                    for song in years[year]
                ]
                years_item.children.append(year_item)
            self.results_store.append(years_item)

        # Artists category
        if artists:
            artists_item = FileItem(
                name=f"Artists ({len(artists)})",
                path="",
                icon_name="system-users-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            artists_item.children = []
            for artist in sorted(artists.keys()):
                artist_item = FileItem(
                    name=f"{artist} ({len(artists[artist])} songs)",
                    path="",
                    icon_name="folder-symbolic",
                    is_directory=True,
                    pixbuf=None,
                )
                artist_item.children = [
                    FileItem(
                        name=song.get("title", "Unknown"),
                        path=song["file"],
                        icon_name="audio-x-generic-symbolic",
                        is_directory=False,
                        pixbuf=None,
                    )
                    for song in artists[artist]
                ]
                artists_item.children.append(artist_item)
            self.results_store.append(artists_item)

        # Albums category
        if albums:
            albums_item = FileItem(
                name=f"Albums ({len(albums)})",
                path="",
                icon_name="media-optical-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            albums_item.children = []
            for album in sorted(albums.keys()):
                album_item = FileItem(
                    name=f"{album} ({len(albums[album])} songs)",
                    path="",
                    icon_name="folder-symbolic",
                    is_directory=True,
                    pixbuf=None,
                )
                album_item.children = [
                    FileItem(
                        name=song.get("title", "Unknown"),
                        path=song["file"],
                        icon_name="audio-x-generic-symbolic",
                        is_directory=False,
                        pixbuf=None,
                    )
                    for song in albums[album]
                ]
                albums_item.children.append(album_item)
            self.results_store.append(albums_item)

        # Songs category
        if songs:
            songs_item = FileItem(
                name=f"Songs ({len(songs)})",
                path="",
                icon_name="audio-x-generic-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            songs_item.children = [
                FileItem(
                    name=f"{song.get('title', 'Unknown')} - {song.get('artist', 'Unknown')}",
                    path=song["file"],
                    icon_name="audio-x-generic-symbolic",
                    is_directory=False,
                    pixbuf=None,
                )
                for song in songs
            ]
            self.results_store.append(songs_item)

        return False
