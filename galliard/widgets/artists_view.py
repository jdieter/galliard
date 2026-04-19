import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio  # noqa: E402

from galliard.models import Artist, Album, Song  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402
from galliard.utils.glib import idle_add_once  # noqa: E402
from galliard.utils.gtk_styling import apply_compact_tree_css  # noqa: E402
from galliard.widgets.mpd_item_row import build_compact_tree_row  # noqa: E402


class ArtistsView(Gtk.ScrolledWindow):
    """Expandable Artist → Album → Song tree for the library."""

    def __init__(self, mpd_client):
        """Build the tree model and schedule the initial load."""
        super().__init__()
        self.mpd_client = mpd_client
        self._current_hovered_image = None
        self.last_preview_popover = None

        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.create_ui()

        # Defer the first fetch until the UI is fully constructed.
        AsyncUIHelper.run_glib_idle_async(self.load_artists)

    def create_ui(self):
        """Build the tree model, column view, and compact-row CSS."""
        self.artists_store = Gio.ListStore.new(Artist)

        # The create_func fires lazily when a row is first expanded, so
        # albums (and their songs) load on demand.
        self.tree_model = Gtk.TreeListModel.new(
            self.artists_store,
            False,  # passthrough
            False,  # autoexpand
            self._create_children_model,
        )

        self.selection = Gtk.SingleSelection.new(self.tree_model)

        self.artists_tree = Gtk.ColumnView.new(self.selection)
        self.artists_tree.set_show_column_separators(False)
        self.artists_tree.set_show_row_separators(False)

        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._item_setup)
        factory.connect("bind", self._item_bind)
        factory.connect("unbind", self._item_unbind)

        column = Gtk.ColumnViewColumn.new("Artists", factory)
        column.set_expand(True)
        self.artists_tree.append_column(column)

        # ColumnView always shows a header; we only have one column so hide it.
        table_header = self.artists_tree.get_first_child()
        if table_header:
            table_header.set_visible(False)

        self.selection.connect("selection-changed", self._on_selection_changed)

        self.set_child(self.artists_tree)

        self.artists_tree.set_name("artists-tree")
        apply_compact_tree_css("artists-tree")

    def _item_setup(self, factory, list_item):
        """Populate the row scaffold shared by all three item types."""
        build_compact_tree_row(
            list_item,
            on_expand=self._on_expander_clicked,
            on_context=self._on_right_click,
            on_play=self._on_play_clicked,
        )

    def _item_bind(self, factory, list_item):
        """Fill the scaffold with the current item (Artist, Album, or Song)."""
        tree_list_row = list_item.get_item()
        item = tree_list_row.get_item()

        if not item:
            return

        # Manual indentation -- we're using a flat ColumnView, not a built-in
        # TreeExpander, so the row has to draw its own depth spacing.
        depth = tree_list_row.get_depth()
        indent_pixels = depth * 24

        is_expandable = isinstance(item, Artist) or isinstance(item, Album)

        if is_expandable:
            list_item.expander.set_margin_start(indent_pixels)
            list_item.expander.set_visible(True)

            is_expanded = tree_list_row.get_expanded()
            icon_name = "pan-down-symbolic" if is_expanded else "pan-end-symbolic"
            list_item.expander.set_icon_name(icon_name)
            list_item.image.set_margin_start(0)

            list_item.play_button.set_visible(True)
        else:
            list_item.expander.set_visible(False)
            # Songs have no expander, so shift the image over by expander-width
            # to keep them aligned with their parent album's label.
            list_item.image.set_margin_start(indent_pixels + 26)
            list_item.play_button.set_visible(False)

        if isinstance(item, Artist):
            list_item.image.set_from_icon_name("performer-symbolic")
            list_item.label.set_text(item.name)
        elif isinstance(item, Album):
            if item.pixbuf:
                list_item.image.set_from_pixbuf(item.pixbuf)
                # Attach a hover-preview controller whenever the row binds
                # to an album with real cover art.
                motion_controller = Gtk.EventControllerMotion.new()
                motion_controller.connect("motion", self._on_tree_motion)
                motion_controller.connect("leave", self._on_tree_leave)
                list_item.image.add_controller(motion_controller)
            else:
                list_item.image.set_from_icon_name("media-optical-symbolic")

            album_text = item.title
            if item.year:
                album_text += f" ({item.year})"
            list_item.label.set_text(album_text)
        elif isinstance(item, Song):
            list_item.image.set_from_icon_name("audio-x-generic-symbolic")

            song_text = item.get_title()
            if item.track:
                song_text = f"{item.track}. {song_text}"
            list_item.label.set_text(song_text)

        # Stash the tree row on the list item so handlers (expander, play,
        # context menu) can look up the current item and depth.
        list_item.tree_list_row = tree_list_row
        item.list_item = list_item

    def _item_unbind(self, factory, list_item):
        """Clear the stashed tree_list_row so recycled rows don't leak state."""
        list_item.tree_list_row = None

    def _create_children_model(self, parent_item):
        """Build the child Gio.ListStore for an Artist or Album parent."""
        if isinstance(parent_item, Artist):
            return self._create_artist_children_model(parent_item)
        if isinstance(parent_item, Album):
            return self._create_album_children_model(parent_item)
        return None

    def _create_artist_children_model(self, artist_item):
        """Create model for artist's albums"""
        if not isinstance(artist_item, Artist):
            return None

        # Create a list store for albums
        child_store = Gio.ListStore.new(Album)

        if not artist_item.children_loaded:
            # Load albums asynchronously
            AsyncUIHelper.run_async_operation(
                self._load_artist_albums,
                lambda result: self._update_artist_albums(
                    artist_item, result, child_store
                ),
                artist_item.name,
            )

            # Show a spinner row until the real album list arrives.
            loading_item = Album(
                title="Loading...",
                artist=artist_item.name,
                icon_name="content-loading-symbolic",
            )
            child_store.append(loading_item)
        else:
            for album in artist_item.albums:
                child_store.append(album)

        return child_store

    async def _load_artist_albums(self, artist_name):
        """Return a year-sorted list of Albums for ``artist_name``.

        Kicks off a per-album background task to fetch cover art and the
        release year; those fill in asynchronously via
        :meth:`_update_album_art_and_year`.
        """
        try:
            albums = await self.mpd_client.async_get_albums_by_artist(artist_name)
        except Exception as e:
            print(f"Error loading albums for {artist_name}: {e}")
            return []

        for album in albums:
            AsyncUIHelper.run_async_operation(
                self._load_album_art_and_year,
                lambda result, album=album: self._update_album_art_and_year(
                    album, result
                ),
                artist_name,
                album.title,
                task_priority=110,
            )

        albums.sort(key=lambda album: album.year if album.year else 9999)
        return albums

    def _update_artist_albums(self, artist, albums, child_store):
        """Replace ``artist``'s loading placeholder with the real album list."""
        artist.albums = albums
        artist.children_loaded = True

        child_store.remove_all()

        for album in artist.albums:
            child_store.append(album)

        idle_add_once(lambda: self.artists_tree.queue_draw())

    async def _load_album_art_and_year(self, artist_name, album_name):
        """Fetch ``(pixbuf, year, songs)`` for an album using its first song."""
        try:
            songs = await self.mpd_client.async_find(
                "artist", artist_name, "album", album_name
            )
            if songs:
                song = songs[0]
                pixbuf = await get_album_art_as_pixbuf(
                    self.mpd_client, song.file, 200
                )

                # MPD's date tag can be "YYYY" or "YYYY-MM-DD"; take the year.
                year = None
                date = song.get("date")
                if date:
                    year_str = str(date).split("-")[0].strip()
                    if year_str.isdigit():
                        year = int(year_str)

                return pixbuf, year, songs
        except Exception as e:
            print(f"Error loading art for {artist_name} - {album_name}: {e}")

        return None, None, []

    def _update_album_art_and_year(self, album, result):
        """Back-fill ``album``'s fetched metadata onto the already-shown row."""
        pixbuf, year, songs = result
        album.pixbuf = pixbuf
        album.year = year
        album.songs = songs

        if hasattr(album, "list_item") and album.list_item:
            if pixbuf:
                album.list_item.image.set_from_pixbuf(pixbuf)
                album.list_item.image.pixbuf_data = pixbuf

                # Hover preview only applies once the real art is loaded.
                motion_controller = Gtk.EventControllerMotion.new()
                motion_controller.connect("motion", self._on_tree_motion)
                motion_controller.connect("leave", self._on_tree_leave)
                album.list_item.image.add_controller(motion_controller)

            if year:
                album_text = f"{album.title} ({year})"
                album.list_item.label.set_text(album_text)

            idle_add_once(self.artists_tree.queue_draw)

    def _create_album_children_model(self, album_item):
        """Return the song list for ``album_item``, sorted by track number."""
        if not isinstance(album_item, Album):
            return None

        songs_store = Gio.ListStore.new(Song)
        if not album_item.songs:
            return songs_store

        def track_sort_key(song):
            track = song.get("track")
            if not track:
                return 9999
            # Track tags are sometimes "5/12" -- take the leading number.
            first = str(track).split("/")[0]
            return int(first) if first.isdigit() else 9999

        for song in sorted(album_item.songs, key=track_sort_key):
            songs_store.append(song)
        album_item.songs_loaded = True
        return songs_store

    def _on_expander_clicked(self, button, list_item):
        """Toggle the expanded state of ``list_item``'s tree row.

        Gtk.TreeListModel calls :meth:`_create_children_model` to build the
        child list on first expansion, so we only flip the expanded flag
        and swap the icon here.
        """
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        if tree_list_row.get_expanded():
            tree_list_row.set_expanded(False)
            button.set_icon_name("pan-end-symbolic")
        else:
            tree_list_row.set_expanded(True)
            button.set_icon_name("pan-down-symbolic")

    def _on_play_clicked(self, button, list_item):
        """Per-row play button: play the entire artist or album."""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        item = tree_list_row.get_item()

        if isinstance(item, Artist):
            AsyncUIHelper.run_async_operation(self._play_artist_songs, None, item.name)
        elif isinstance(item, Album):
            AsyncUIHelper.run_async_operation(self._play_album_songs, None, item)

    def _on_selection_changed(self, selection, position, n_items):
        """Selecting a song row appends it to the playlist and plays it."""
        selected = selection.get_selected_item()
        if not selected:
            return

        item = selected.get_item()
        if not item:
            return

        if isinstance(item, Song) and self.mpd_client.is_connected():
            self.mpd_client.add_to_playlist(item.file)
            playlist = self.mpd_client.get_current_playlist()
            if playlist:
                # Play the song just appended (last item in the playlist).
                self.mpd_client.client.play(len(playlist) - 1)

    def _on_tree_motion(self, controller, x, y):
        """Show the hover-preview popover when the cursor is over album art."""
        image = controller.get_widget()

        if hasattr(image, "pixbuf_data") and image.pixbuf_data:
            widget_position = image.translate_coordinates(self.artists_tree, x, y)

            if not widget_position:
                return

            tree_x, tree_y = widget_position

            if self._current_hovered_image != image:
                self._current_hovered_image = image

            self._show_preview(image.pixbuf_data, tree_x, tree_y)

    def _on_tree_leave(self, controller):
        """Hide the hover-preview popover once the cursor leaves the art."""
        image = controller.get_widget()
        if image == self._current_hovered_image:
            self._hide_preview()

    def _show_preview(self, pixbuf, x, y):
        """Pop up a 200x200 preview of ``pixbuf`` near (x, y)."""
        if not self.last_preview_popover:
            self.last_preview_popover = Gtk.Popover()
            self.last_preview_popover.set_autohide(True)

            self.preview_image = Gtk.Image()
            self.preview_image.set_size_request(200, 200)

            self.last_preview_popover.set_child(self.preview_image)
            self.last_preview_popover.set_parent(self.artists_tree)

        self.preview_image.set_from_pixbuf(pixbuf)

        # Offset from the cursor so the popover doesn't sit on top of the
        # row being hovered.
        rect = Gdk.Rectangle()
        rect.x = int(x) + 20
        rect.y = int(y)
        rect.width = 1
        rect.height = 1

        self.last_preview_popover.set_pointing_to(rect)
        self.last_preview_popover.popup()

    def _hide_preview(self):
        """Dismiss the hover-preview popover."""
        self._current_hovered_image = None
        if self.last_preview_popover:
            self.last_preview_popover.popdown()

    def _on_right_click(self, gesture, n_press, x, y, list_item):
        """Pop up an Append / Replace menu for the right-clicked row."""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        item = tree_list_row.get_item()
        if not item:
            return

        menu_items = [
            {
                "label": "Append",
                "action": "append",
                "callback": lambda: self._on_context_menu_action(item, replace=False),
            },
            {
                "label": "Replace",
                "action": "replace",
                "callback": lambda: self._on_context_menu_action(item, replace=True),
            },
        ]

        ContextMenu.create_menu_with_actions(
            list_item.get_child(), menu_items, "row", x, y,
        )

    def _on_context_menu_action(self, item, replace):
        """Dispatch the chosen Append/Replace action to the right player method."""
        if isinstance(item, Artist):
            AsyncUIHelper.run_async_operation(
                self._play_artist_songs, None, item.name, replace
            )
        elif isinstance(item, Album):
            AsyncUIHelper.run_async_operation(
                self._play_album_songs, None, item, replace
            )
        elif isinstance(item, Song):
            AsyncUIHelper.run_async_operation(self._play_song, None, item.file, replace)

    async def _play_artist_songs(self, artist_name, replace=True):
        """Queue every song by ``artist_name``; replace + autoplay when asked."""
        try:
            if replace:
                await self.mpd_client.async_clear_playlist()

            songs = await self.mpd_client.async_get_songs_by_artist(artist_name)
            if songs:
                await self.mpd_client.async_add_songs_to_playlist(
                    [song.file for song in songs]
                )

                if replace:
                    await self.mpd_client.async_play(0)
        except Exception as e:
            print(f"Error playing artist songs: {e}")

    async def _play_album_songs(self, album, replace=True):
        """Queue ``album``'s songs in track order; replace + autoplay when asked."""
        try:
            if replace:
                await self.mpd_client.async_clear_playlist()

            songs = await self.mpd_client.async_find(
                "artist", album.artist, "album", album.title
            )
            if songs:
                def track_sort_key(song):
                    track = song.get("track")
                    if not track:
                        return 9999
                    first = str(track).split("/")[0]
                    return int(first) if first.isdigit() else 9999

                songs.sort(key=track_sort_key)

                await self.mpd_client.async_add_songs_to_playlist(
                    [song.file for song in songs]
                )

                if replace:
                    await self.mpd_client.async_play(0)
        except Exception as e:
            print(f"Error playing album songs: {e}")

    async def _play_song(self, file_path, replace=True):
        """Queue a single song; replace + autoplay when asked."""
        try:
            if replace:
                await self.mpd_client.async_clear_playlist()

            await self.mpd_client.async_add_songs_to_playlist([file_path])

            self.mpd_client.client.play(0 if replace else -1)
        except Exception as e:
            print(f"Error playing song: {e}")

    async def load_artists(self):
        """Populate ``self.artists_store`` with every artist in the library."""
        if not self.mpd_client.is_connected():
            return False

        try:
            self.artists_store.remove_all()

            artists = await self.mpd_client.async_get_artists()
            if artists:
                artists.sort(key=lambda artist: get_sort_key(artist.name))
                for artist in artists:
                    if artist.name:
                        self.artists_store.append(artist)

            idle_add_once(lambda: self.artists_tree.queue_draw())
        except Exception as e:
            print(f"Error loading artists: {e}")

        return False

    def refresh(self):
        """Re-fetch and redisplay the artist list."""
        AsyncUIHelper.run_async_operation(self.load_artists, None)
