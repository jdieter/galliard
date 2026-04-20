import gi
import logging

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio  # noqa: E402

from galliard.models import FileItem  # noqa: E402
from galliard.utils.album_art import fetch_art_async  # noqa: E402
from galliard.utils.artists import group_artist_names  # noqa: E402
from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402
from galliard.utils.gtk_styling import apply_compact_tree_css  # noqa: E402
from galliard.widgets.mpd_item_row import build_compact_tree_row  # noqa: E402


class SearchResultsView(Gtk.ScrolledWindow):
    """Grouped search results: Artist / Album / Title / Date hierarchies."""

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
        self.results_tree.set_name("search-results-tree")
        apply_compact_tree_css("search-results-tree")

    def _item_setup(self, factory, list_item):
        """Setup function for items"""
        build_compact_tree_row(
            list_item,
            on_expand=self._on_expander_clicked,
            on_context=self._on_item_right_click,
        )

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
            logging.error("Error performing search: %s", e)

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
                children = self._build_artist_hierarchy(
                    unique_results, search_term, filter_to_search=True,
                )
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
        track = song.get('track')
        title = song.get('title') or 'Unknown'

        if track:
            # Handle track numbers like "1/12" or "1"
            if isinstance(track, str) and '/' in track:
                track = track.split('/')[0]
            return f"{track}. {title}"
        return title

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

        song_artist = song.get('artist')
        grouped_artist = song.get('albumartist')
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
        album = song.get('album') or 'Unknown'
        artist = song.get('artist') or 'Unknown'

        title_item = FileItem(
            name=f"{title} - {album} - {artist}",
            path=song.file,
            icon_name="audio-x-generic-symbolic",
            is_directory=False,
            pixbuf=None,
        )

        # Load album art for this song into the FileItem's pixbuf slot.
        fetch_art_async(
            self.mpd_conn,
            song,
            200,
            lambda pixbuf, item=title_item: self._apply_art_to_item(item, pixbuf),
            task_id=f"load_title_art_search_{self.counter}",
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

        # Load album art from the first song into the FileItem's pixbuf slot.
        if songs:
            fetch_art_async(
                self.mpd_conn,
                songs[0],
                200,
                lambda pixbuf, item=album_item: self._apply_art_to_item(item, pixbuf),
                task_id=f"load_album_art_search_{self.counter}",
            )

        return album_item

    def _build_date_hierarchy(self, songs, search_term):
        """Build year → artist → album → song hierarchy"""
        years = {}

        for song in songs:
            year = song.get("date")
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

    def _build_artist_hierarchy(self, songs, search_term, filter_to_search=False):
        """Build artist → album → song hierarchy.

        Raw artist *and* albumartist tags are both fed into
        :func:`group_artist_names` so a song tagged with a compound
        artist ("Alpha / Beta") or with a mismatched albumartist shows
        up under every relevant display row. A song belongs to a row
        when the row's alias set contains its raw artist tag or its
        raw albumartist tag.

        When ``filter_to_search`` is True, only rows whose display name
        contains ``search_term`` (case-insensitive) are emitted --
        prevents splitting ``"Chris / Steven"`` on a ``"steven"`` search
        from surfacing ``"Chris"`` as its own row.
        """
        all_raws = []
        seen_raws = set()
        for song in songs:
            for raw in (
                song.get("artist") or "Unknown",
                song.get("albumartist"),
            ):
                if raw and raw not in seen_raws:
                    seen_raws.add(raw)
                    all_raws.append(raw)

        needle = search_term.casefold() if filter_to_search and search_term else None

        artist_items = []
        groups = group_artist_names(all_raws)
        for display, aliases in sorted(groups, key=lambda g: get_sort_key(g[0])):
            if needle and needle not in display.casefold():
                continue

            alias_set = set(aliases)
            bucket = []
            seen_files = set()
            for song in songs:
                artist_raw = song.get("artist") or "Unknown"
                aa_raw = song.get("albumartist")
                in_track = artist_raw in alias_set
                in_album = bool(aa_raw) and aa_raw in alias_set
                if (in_track or in_album) and song.file not in seen_files:
                    seen_files.add(song.file)
                    bucket.append(song)

            if not bucket:
                continue

            artist_item = FileItem(
                name=display,
                path="",
                icon_name="system-users-symbolic",
                is_directory=True,
                pixbuf=None,
            )
            artist_item.children = self._build_album_hierarchy(bucket, search_term)
            artist_items.append(artist_item)

        return artist_items

    def _build_album_hierarchy(self, songs, search_term):
        """Build album → song hierarchy, sorted by year then name.

        Keys by (album_name, albumartist_or_artist, year) so two distinct
        releases that happen to share a title (different artists, reissues,
        etc.) stay separate. The displayed row is still just the album name.
        """
        groups: dict[tuple, list] = {}

        for song in songs:
            album = song.get("album") or "Unknown"
            artist = song.get("albumartist") or song.get("artist") or "Unknown"
            year = song.get("date")
            groups.setdefault((album, artist, year), []).append(song)

        def sort_key(key):
            album_name, artist, year = key
            year_sort = int(year) if year and str(year).isdigit() else 9999
            return (year_sort, get_sort_key(album_name), artist)

        album_items = []
        for key in sorted(groups.keys(), key=sort_key):
            album_name, _artist, _year = key
            album_items.append(
                self._create_album_file_item(album_name, groups[key], search_term)
            )
        return album_items

    def _apply_art_to_item(self, file_item, pixbuf):
        """Store the fetched pixbuf on the FileItem and refresh any bound row."""
        if not pixbuf:
            return
        file_item.pixbuf = pixbuf
        file_item.icon_name = None
        if file_item.list_item is not None:
            file_item.list_item.image.set_from_pixbuf(pixbuf)
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
            logging.error("Error adding song to playlist %s: %s", file_path, e)

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
            logging.error("Error adding items to playlist: %s", e)

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
