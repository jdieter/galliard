import gi
import logging

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio  # noqa: E402

from galliard.models import FileItem  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402


class SearchResultsView(Gtk.ScrolledWindow):
    """Search results view with hierarchical organization"""

    def __init__(self, mpd_conn):
        super().__init__()
        self.mpd_conn = mpd_conn
        self.counter = 0

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

        # Apply CSS for compact rows
        self._apply_css()

    def _apply_css(self):
        """Apply CSS styling to make the tree more compact"""
        # First, make sure the results_tree has a name so we can target it with CSS
        self.results_tree.set_name("search-results-tree")

        # Create a CSS provider
        css_provider = Gtk.CssProvider()

        # Define the CSS to reduce row height
        css = b"""
        #search-results-tree {
            /* Reduce the overall padding in the tree */
            padding: 0;
        }

        #search-results-tree row {
            /* Reduce the vertical padding for each row */
            padding-top: 0px;
            padding-bottom: 0px;
            min-height: 20px; /* Adjust this value to get the desired row height */
        }

        #search-results-tree cell {
            /* Reduce the vertical padding for each row */
            padding-top: 1px;
            padding-bottom: 1px;
            min-height: 20px; /* Adjust this value to get the desired row height */
        }

        .compact {
            padding-top: 0;
            padding-bottom: 0;
            margin-top: 0;
            margin-bottom: 0;
        }

        #compact-expander {
            /* Make expander button more compact */
            padding-top: 0;
            padding-bottom: 0;
            min-height: 16px;
            min-width: 16px;
        }

        #compact-expander image {
            /* Make the icon inside the button smaller */
            -gtk-icon-size: 12px;
        }
        """

        # Load the CSS
        css_provider.load_from_data(css)

        # Add the CSS provider to the display
        if display := Gdk.Display.get_default():
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def _item_setup(self, factory, list_item):
        """Setup function for items"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_margin_start(0)
        box.set_margin_end(0)
        box.set_margin_top(0)
        box.set_margin_bottom(0)

        # Expander for categories
        expander = Gtk.Button.new_from_icon_name("pan-end-symbolic")
        expander.add_css_class("flat")
        expander.set_visible(False)
        expander.set_name("compact-expander")
        box.append(expander)

        # Icon/album art
        image = Gtk.Image()
        image.set_size_request(20, 20)
        image.add_css_class("compact")
        box.append(image)

        # Label
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.add_css_class("compact")
        box.append(label)

        list_item.set_child(box)
        list_item.image = image
        list_item.label = label
        list_item.expander = expander

        expander.connect("clicked", self._on_expander_clicked, list_item)

        # Add context menu support
        gesture_click = Gtk.GestureClick.new()
        gesture_click.set_button(3)  # Right mouse button
        gesture_click.connect("pressed", self._on_item_right_click, list_item)
        box.add_controller(gesture_click)

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
        """Perform search across multiple types and group by search type"""
        if not query.strip():
            idle_add_once(lambda: self.results_store.remove_all())
            return

        try:
            # Group results by search type
            results_by_type = {}
            for search_type in ["artist", "album", "title", "date"]:
                results = await self.mpd_conn.async_search(search_type, query)
                if results:
                    results_by_type[search_type] = results

            # Build result tree grouped by search type
            idle_add_once(self._build_results_tree_by_type, results_by_type, query)

        except Exception as e:
            print(f"Error performing search: {e}")

    def _build_results_tree_by_type(self, results_by_type, search_term):
        """Build the hierarchical results tree grouped by search type"""
        self.results_store.remove_all()

        search_type_labels = {
            "artist": ("Artist Matches", "system-users-symbolic"),
            "album": ("Album Matches", "media-optical-symbolic"),
            "title": ("Title Matches", "audio-x-generic-symbolic"),
            "date": ("Date Matches", "x-office-calendar-symbolic"),
        }

        for search_type in ["date", "artist", "album", "title"]:
            if search_type not in results_by_type:
                continue

            results = results_by_type[search_type]
            label, icon = search_type_labels[search_type]

            # Remove duplicates based on file path
            seen = set()
            unique_results = []
            for item in results:
                if item.file not in seen:
                    seen.add(item.file)
                    unique_results.append(item)

            # Build hierarchical structure based on search type
            if search_type == "date":
                children = self._build_date_hierarchy(unique_results, search_term)
            elif search_type == "artist":
                children = self._build_artist_hierarchy(unique_results, search_term)
            elif search_type == "album":
                children = self._build_album_hierarchy(unique_results, search_term)
            else:  # title
                children = [
                    self._create_title_file_item(song)
                    for song in unique_results
                ]

            # Create top-level category with count of direct children
            type_item = FileItem(
                name=f"{label} ({len(children)})",
                path="",
                icon_name=icon,
                is_directory=True,
                pixbuf=None,
            )
            type_item.children = children

            self.results_store.append(type_item)

        return False

    def _format_track_title(self, song):
        """Format song title with track number if available"""
        track = getattr(song, 'track', None)
        title = getattr(song, 'title', 'Unknown')

        if track:
            # Handle track numbers like "1/12" or "1"
            if isinstance(track, str) and '/' in track:
                track = track.split('/')[0]
            return f"{track}. {title}"
        return title

    def _get_field_value(self, song, field):
        """Get a field value from a song, handling list values"""
        value = getattr(song, field, None)
        if isinstance(value, list):
            return value[0] if value else None
        return value

    def _create_album_sort_key(self, album_years):
        """Create a sort key function for albums based on year then name"""
        def album_sort_key(album):
            year = album_years.get(album)
            year_sort = int(year) if year and str(year).isdigit() else 9999
            return (year_sort, get_sort_key(album))
        return album_sort_key

    def _create_song_file_item(self, song, search_term):
        """Create a FileItem for a song with optional artist suffix"""
        title = self._format_track_title(song)

        song_artist = self._get_field_value(song, 'artist')
        grouped_artist = self._get_field_value(song, 'albumartist')
        if grouped_artist is not None and song_artist is not None and search_term.lower() not in grouped_artist.lower():
            name = f"{title} - {song_artist}"
        else:
            name = title

        return FileItem(
            name=name,
            path=song.file,
            icon_name="audio-x-generic-symbolic",
            is_directory=False,
            pixbuf=None,
        )

    def _create_title_file_item(self, song):
        """Create a FileItem for a title match with album art"""
        title = self._format_track_title(song)
        album = getattr(song, 'album', 'Unknown')
        artist = getattr(song, 'artist', 'Unknown')

        title_item = FileItem(
            name=f"{title} - {album} - {artist}",
            path=song.file,
            icon_name="audio-x-generic-symbolic",
            is_directory=False,
            pixbuf=None,
        )

        # Load album art for this song
        AsyncUIHelper.run_async_operation(
            self._load_album_art,
            lambda result, item=title_item: self._update_item_art(item, result),
            song.file,
            task_id=f"load_title_art_search_{self.counter}",
            task_priority=110,  # Lower priority for album art loading
        )
        self.counter += 1

        return title_item

    def _create_album_file_item(self, album, songs, search_term):
        """Create a FileItem for an album with its songs"""
        album_item = FileItem(
            name=album,
            path="",
            icon_name="media-optical-symbolic",
            is_directory=True,
            pixbuf=None,
        )
        album_item.children = [
            self._create_song_file_item(song, search_term)
            for song in songs
        ]

        # Load album art from the first song
        if songs:
            AsyncUIHelper.run_async_operation(
                self._load_album_art,
                lambda result, item=album_item: self._update_item_art(item, result),
                songs[0].file,
                task_id=f"load_album_art_search_{self.counter}",
                task_priority=110,  # Lower priority for album art loading
            )

        return album_item

    def _build_date_hierarchy(self, songs, search_term):
        """Build year → artist → album → song hierarchy"""
        years = {}

        for song in songs:
            year = self._get_field_value(song, "date")
            if year is None:
                year = "Unknown"
            if year not in years:
                years[year] = []
            years[year].append(song)

        # Build FileItem tree
        year_items = []
        for year in sorted(years.keys(), reverse=True):
            year_item = FileItem(
                name=str(year),
                path="",
                icon_name="x-office-calendar-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            # Use _build_artist_hierarchy for this year's songs
            year_item.children = self._build_artist_hierarchy(years[year], search_term)
            year_items.append(year_item)

        return year_items

    def _build_artist_hierarchy(self, songs, search_term):
        """Build artist → album → song hierarchy"""
        artists = {}

        for song in songs:
            artist = self._get_field_value(song, "albumartist")
            if artist is None:
                artist = self._get_field_value(song, "artist")
            if artist is None:
                artist = "Unknown"
            if artist not in artists:
                artists[artist] = []
            artists[artist].append(song)

        # Build FileItem tree
        artist_items = []
        for artist in sorted(artists.keys()):
            artist_item = FileItem(
                name=artist,
                path="",
                icon_name="system-users-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            # Use _build_album_hierarchy for this artist's songs
            artist_item.children = self._build_album_hierarchy(artists[artist], search_term)
            artist_items.append(artist_item)

        return artist_items

    def _build_album_hierarchy(self, songs, search_term):
        """Build album → song hierarchy, sorted by year then name"""
        albums = {}
        album_years = {}

        for song in songs:
            album = self._get_field_value(song, "album")
            if album is None:
                album = "Unknown"
            year = getattr(song, "date", None)
            if isinstance(year, list):
                year = year[0] if year else None

            if album not in albums:
                albums[album] = []
                album_years[album] = year

            albums[album].append(song)
            # Prefer earliest year if multiple
            if year and (album_years[album] is None or year < album_years[album]):
                album_years[album] = year

        # Build FileItem tree
        album_sort_key = self._create_album_sort_key(album_years)
        album_items = []
        for album in sorted(albums.keys(), key=album_sort_key):
            album_item = self._create_album_file_item(
                album, albums[album], search_term
            )
            album_items.append(album_item)

        return album_items

    async def _load_album_art(self, audio_file):
        """Load album art for an audio file"""
        try:
            return await get_album_art_as_pixbuf(
                self.mpd_conn, audio_file, 200
            )
        except Exception as e:
            print(f"Error getting album art for {audio_file}: {e}")
            return None

    def _update_item_art(self, file_item, pixbuf):
        """Update file item with album art"""
        if pixbuf:
            # Always store the pixbuf on the file_item
            file_item.pixbuf = pixbuf
            file_item.icon_name = None

            # If the item is already bound, update the display immediately
            if file_item.list_item is not None:
                file_item.list_item.image.set_from_pixbuf(pixbuf)
                # Notify model that item has changed
                idle_add_once(self.results_tree.queue_draw)

    def _on_item_right_click(self, gesture, n_press, x, y, list_item):
        """Handle right-click on items"""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        file_item = tree_list_row.get_item()
        if not file_item:
            return


        menu_items = [
            {
                "label": "Append",
                "action": "append",
                "callback": lambda: self._on_context_menu_action(
                    file_item, replace=False
                ),
            },
            {
                "label": "Replace",
                "action": "replace",
                "callback": lambda: self._on_context_menu_action(
                    file_item, replace=True
                ),
            },
        ]

        ContextMenu.create_menu_with_actions(
            list_item.get_child(),  # Parent widget
            menu_items,  # Menu items
            "row",  # Action group name
            x,  # X position
            y,  # Y position
        )

    def _on_context_menu_action(self, file_item, replace):
        """Handle context menu actions"""
        # Launch appropriate async operation based on the selection
        if file_item.is_directory:
            # For directories, add all children recursively
            AsyncUIHelper.run_async_operation(
                self.add_items_to_playlist, None, file_item, replace
            )
        else:
            # For individual songs
            AsyncUIHelper.run_async_operation(
                self.add_song_to_playlist, None, file_item.path, replace
            )

    async def add_song_to_playlist(self, file_path, replace=False):
        """Add a single song to the playlist"""
        try:
            # Clear playlist if replacing
            if replace:
                await self.mpd_conn.async_clear_playlist()

            await self.mpd_conn.async_add_songs_to_playlist([file_path])

            if replace:
                await self.mpd_conn.async_play(0)
        except Exception as e:
            print(f"Error adding song to playlist {file_path}: {e}")

    async def add_items_to_playlist(self, file_item, replace=False):
        """Add items (directory or hierarchy) to the playlist"""
        try:
            # Clear playlist if replacing
            if replace:
                await self.mpd_conn.async_clear_playlist()

            # Collect all song paths from this item and its children
            songs = self._collect_all_songs(file_item)

            # Add all songs to playlist
            await self.mpd_conn.async_add_songs_to_playlist(songs)

            if replace:
                await self.mpd_conn.async_play(0)
        except Exception as e:
            print(f"Error adding items to playlist: {e}")

    def _collect_all_songs(self, file_item):
        """Recursively collect all song paths from a file item and its children"""
        songs = []

        if not file_item.is_directory:
            # It's a song, add its path
            if file_item.path:
                songs.append(file_item.path)
        else:
            # It's a directory/category, recurse through children
            for child in file_item.children:
                songs.extend(self._collect_all_songs(child))

        return songs
