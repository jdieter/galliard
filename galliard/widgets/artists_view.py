import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio, GLib  # noqa: E402

from galliard.models import Artist, Album, Song  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402
from galliard.utils.context_menu import ContextMenu  # noqa: E402


class ArtistsView(Gtk.ScrolledWindow):
    """Artists view for the library"""

    def __init__(self, mpd_client):
        super().__init__()
        self.mpd_client = mpd_client
        self._current_hovered_image = None
        self.last_preview_popover = None

        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Create UI elements
        self.create_ui()

        # Load artists on idle to ensure UI is constructed first
        AsyncUIHelper.run_glib_idle_async(self.load_artists)

    def create_ui(self):
        """Create the artists view UI"""
        # Create a list store for our artists
        self.artists_store = Gio.ListStore.new(Artist.__gtype__)

        # Create tree list model to handle the hierarchy
        self.tree_model = Gtk.TreeListModel.new(
            self.artists_store,
            False,  # Passthrough
            False,  # Set autoexpand to False to prevent automatic expansion
            self._create_artist_children_model,
        )

        # Create selection model
        self.selection = Gtk.SingleSelection.new(self.tree_model)

        # Create column view
        self.artists_tree = Gtk.ColumnView.new(self.selection)
        self.artists_tree.set_show_column_separators(False)
        self.artists_tree.set_show_row_separators(False)

        # Create factory for artists items
        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._item_setup)
        factory.connect("bind", self._item_bind)
        factory.connect("unbind", self._item_unbind)

        # Create column for artists
        column = Gtk.ColumnViewColumn.new("Artists", factory)
        column.set_expand(True)
        self.artists_tree.append_column(column)

        # Hide the table header
        table_header = self.artists_tree.get_first_child()
        table_header.set_visible(False)

        # Connect signals for handling selection
        self.selection.connect("selection-changed", self._on_selection_changed)

        # Add the tree to the scrolled window
        self.set_child(self.artists_tree)

        # Apply CSS for compact rows
        self._apply_css()

    def _apply_css(self):
        """Apply CSS styling to make the tree more compact"""
        # First, make sure the tree has a name so we can target it with CSS
        self.artists_tree.set_name("artists-tree")

        # Create a CSS provider
        css_provider = Gtk.CssProvider()

        # Define the CSS to reduce row height
        css = b"""
        #artists-tree {
            /* Reduce the overall padding in the tree */
            padding: 0;
        }

        #artists-tree row {
            /* Reduce the vertical padding for each row */
            padding-top: 0px;
            padding-bottom: 0px;
            min-height: 20px; /* Adjust this value to get the desired row height */
        }

        #artists-tree cell {
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
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _item_setup(self, factory, list_item):
        """Setup function for tree items (artists, albums, songs)"""
        # Create box for the row
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_margin_start(0)
        box.set_margin_end(0)
        box.set_margin_top(0)
        box.set_margin_bottom(0)

        # Expander widget for expandable items
        expander = Gtk.Button.new_from_icon_name("pan-end-symbolic")
        expander.add_css_class("flat")
        expander.set_visible(False)  # Initially hidden
        expander.set_name("compact-expander")
        box.append(expander)

        # Image for icon or album art
        image = Gtk.Image()
        image.set_size_request(20, 20)
        image.add_css_class("compact")
        box.append(image)

        # Label for item name
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.add_css_class("compact")
        box.append(label)

        # Play button (visible only when needed)
        play_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        play_button.add_css_class("flat")
        play_button.set_tooltip_text("Play")
        play_button.set_visible(False)
        box.append(play_button)

        # Store widgets in list item
        list_item.set_child(box)

        # Store references to widgets for later access
        list_item.image = image
        list_item.label = label
        list_item.expander = expander
        list_item.play_button = play_button

        # Connect expander button signal
        expander.connect("clicked", self._on_expander_clicked, list_item)
        play_button.connect("clicked", self._on_play_clicked, list_item)

        # Add context menu support
        gesture_click = Gtk.GestureClick.new()
        gesture_click.set_button(3)  # Right mouse button
        gesture_click.connect("pressed", self._on_right_click, list_item)
        box.add_controller(gesture_click)

    def _item_bind(self, factory, list_item):
        """Bind item data to widgets"""
        # Get the tree list row
        tree_list_row = list_item.get_item()

        # Get the actual item from the row
        item = tree_list_row.get_item()

        if not item:
            return

        # Calculate indentation based on depth level
        depth = tree_list_row.get_depth()
        indent_pixels = depth * 24  # 24 pixels per level

        # Determine the type of item and set appropriate UI
        is_expandable = isinstance(item, Artist) or isinstance(item, Album)

        if is_expandable:
            # Set margin_start to handle indentation
            list_item.expander.set_margin_start(indent_pixels)

            # Show expander for expandable items
            list_item.expander.set_visible(True)

            # Update expander icon based on expanded state
            is_expanded = tree_list_row.get_expanded()
            icon_name = "pan-down-symbolic" if is_expanded else "pan-end-symbolic"
            list_item.expander.set_icon_name(icon_name)
            list_item.image.set_margin_start(0)

            # Show play button for artists and albums
            list_item.play_button.set_visible(True)
        else:
            list_item.expander.set_visible(False)
            list_item.image.set_margin_start(indent_pixels + 26)
            list_item.play_button.set_visible(False)

        # Handle icon or pixbuf based on item type
        if isinstance(item, Artist):
            list_item.image.set_from_icon_name("performer-symbolic")
            list_item.label.set_text(item.name)
        elif isinstance(item, Album):
            if item.pixbuf:
                list_item.image.set_from_pixbuf(item.pixbuf)
                # Add motion controller for hover effects on album art
                motion_controller = Gtk.EventControllerMotion.new()
                motion_controller.connect("motion", self._on_tree_motion)
                motion_controller.connect("leave", self._on_tree_leave)
                list_item.image.add_controller(motion_controller)
            else:
                list_item.image.set_from_icon_name("media-optical-symbolic")

            # Display album name with year if available
            album_text = item.title
            if item.year:
                album_text += f" ({item.year})"
            list_item.label.set_text(album_text)
        elif isinstance(item, Song):
            list_item.image.set_from_icon_name("audio-x-generic-symbolic")

            # Display track number and title
            song_text = item.title
            if item.track:
                song_text = f"{item.track}. {song_text}"
            list_item.label.set_text(song_text)

        # Store the row for later access
        list_item.tree_list_row = tree_list_row
        item.list_item = list_item

    def _item_unbind(self, factory, list_item):
        """Clean up when item is unbound"""
        list_item.tree_list_row = None

    def _create_artist_children_model(self, artist_item):
        """Create model for artist's albums"""
        if not isinstance(artist_item, Artist):
            return None

        # Create a list store for albums
        child_store = Gio.ListStore.new(Album.__gtype__)

        if not artist_item.children_loaded:
            # Load albums asynchronously
            AsyncUIHelper.run_async_operation(
                self._load_artist_albums,
                lambda result: self._update_artist_albums(
                    artist_item, result, child_store
                ),
                artist_item.name,
            )

            # Add loading placeholder
            loading_item = Album(
                title="Loading...",
                artist=artist_item.name,
                icon_name="content-loading-symbolic",
            )
            child_store.append(loading_item)
        else:
            # Add existing albums
            for album in artist_item.albums:
                child_store.append(album)

        return child_store

    async def _load_artist_albums(self, artist_name):
        """Load all albums by an artist"""
        albums = []
        try:
            # Get all albums by this artist
            album_list = await self.mpd_client.async_get_albums_by_artist(artist_name)

            # Create Album objects
            for album_name in album_list:
                album = Album(title=album_name, artist=artist_name)
                albums.append(album)

                # Load album art asynchronously
                AsyncUIHelper.run_async_operation(
                    self._load_album_art_and_year,
                    lambda result, album=album: self._update_album_art_and_year(
                        album, result
                    ),
                    artist_name,
                    album_name,
                    task_priority=110,  # Lower priority for album art loading
                )
        except Exception as e:
            print(f"Error loading albums for {artist_name}: {e}")

        # Sort albums by year
        albums.sort(key=lambda album: album.year if album.year else 9999)
        return albums

    def _update_artist_albums(self, artist, albums, child_store):
        """Update artist with loaded albums"""
        artist.albums = albums
        artist.children_loaded = True

        # Update the store directly (remove loading placeholder)
        child_store.remove_all()

        # Add all albums
        for album in artist.albums:
            child_store.append(album)

        # Force UI update
        GLib.idle_add(lambda: self.artists_tree.queue_draw())

    async def _load_album_art_and_year(self, artist_name, album_name):
        """Load album art and year for an album"""
        try:
            # Find a song from this album to get its art
            songs = await self.mpd_client.async_find(
                "artist", artist_name, "album", album_name
            )
            if songs:
                # Get the first song to fetch album art
                song = songs[0]
                pixbuf = await get_album_art_as_pixbuf(
                    self.mpd_client, song["file"], 200
                )

                # Extract year from date tag if available
                year = None
                if "date" in song:
                    # Try to extract year from date string (could be YYYY, YYYY-MM-DD, etc.)
                    year_str = song["date"].split("-")[0].strip()
                    if year_str.isdigit():
                        year = int(year_str)

                return pixbuf, year, songs
        except Exception as e:
            print(f"Error loading art for {artist_name} - {album_name}: {e}")

        return None, None, []

    def _update_album_art_and_year(self, album, result):
        """Update album with art and year information"""
        pixbuf, year, songs = result
        album.pixbuf = pixbuf
        album.year = year
        album.songs = songs  # Store songs for later use

        # Update the UI if this album is displayed
        if hasattr(album, "list_item") and album.list_item:
            if pixbuf:
                album.list_item.image.set_from_pixbuf(pixbuf)
                album.list_item.image.pixbuf_data = pixbuf

                # Add motion controller for hover effects
                motion_controller = Gtk.EventControllerMotion.new()
                motion_controller.connect("motion", self._on_tree_motion)
                motion_controller.connect("leave", self._on_tree_leave)
                album.list_item.image.add_controller(motion_controller)

            # Update album text with year if available
            if year:
                album_text = f"{album.title} ({year})"
                album.list_item.label.set_text(album_text)

            GLib.idle_add(self.artists_tree.queue_draw)

    def _create_album_children_model(self, album_item):
        """Create model for album's songs"""
        if not isinstance(album_item, Album):
            return None

        # Create a list store for songs
        songs_store = Gio.ListStore.new(Song.__gtype__)

        if not album_item.songs_loaded and hasattr(album_item, "songs"):
            # Create Song objects from the songs list
            for song_data in album_item.songs:
                # Extract track number
                track = None
                if "track" in song_data:
                    track_parts = song_data["track"].split("/")
                    if track_parts[0].isdigit():
                        track = int(track_parts[0])

                # Create song object
                song = Song(
                    title=song_data.get("title", song_data["file"].split("/")[-1]),
                    artist=song_data.get("artist", album_item.artist),
                    album=album_item.name,
                    track=track,
                    file=song_data["file"],
                )
                songs_store.append(song)

            # Mark as loaded
            album_item.songs_loaded = True

            # Sort songs by track number
            songs_list = []
            for i in range(songs_store.get_n_items()):
                songs_list.append(songs_store.get_item(i))

            songs_list.sort(key=lambda song: song.track if song.track else 9999)

            # Update store with sorted songs
            songs_store.remove_all()
            for song in songs_list:
                songs_store.append(song)

        return songs_store

    def _on_expander_clicked(self, button, list_item):
        """Handle expander button click"""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        # Toggle expanded state
        is_expanded = tree_list_row.get_expanded()
        item = tree_list_row.get_item()

        # Handle expansion based on item type
        if isinstance(item, Artist):
            if not is_expanded:
                tree_list_row.set_expanded(True)
                button.set_icon_name("pan-down-symbolic")
            else:
                tree_list_row.set_expanded(False)
                button.set_icon_name("pan-end-symbolic")
        elif isinstance(item, Album):
            if not is_expanded:
                # Create children model dynamically if it's an album
                if not hasattr(item, "children_model"):
                    item.children_model = self._create_album_children_model(item)
                    tree_list_row.set_children_model(item.children_model)

                tree_list_row.set_expanded(True)
                button.set_icon_name("pan-down-symbolic")
            else:
                tree_list_row.set_expanded(False)
                button.set_icon_name("pan-end-symbolic")

    def _on_play_clicked(self, button, list_item):
        """Handle play button click"""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        item = tree_list_row.get_item()

        # Handle play action based on item type
        if isinstance(item, Artist):
            AsyncUIHelper.run_async_operation(self._play_artist_songs, None, item.name)
        elif isinstance(item, Album):
            AsyncUIHelper.run_async_operation(self._play_album_songs, None, item)

    def _on_selection_changed(self, selection, position, n_items):
        """Handle selection in the tree"""
        selected = selection.get_selected_item()
        if not selected:
            return

        item = selected.get_item()
        if not item:
            return

        # Play song if a song is selected
        if isinstance(item, Song) and self.mpd_client.is_connected():
            self.mpd_client.add_to_playlist(item.file)
            # Get updated playlist
            playlist = self.mpd_client.get_current_playlist()
            # Play the song that was just added (last in playlist)
            if playlist:
                self.mpd_client.client.play(len(playlist) - 1)

    def _on_tree_motion(self, controller, x, y):
        """Handle mouse motion over tree to detect hovering over album art"""
        # Get the widget from the controller
        image = controller.get_widget()

        # Only process images with album art
        if hasattr(image, "pixbuf_data") and image.pixbuf_data:
            # Convert widget coordinates to window coordinates
            widget_position = image.translate_coordinates(self.artists_tree, x, y)

            if not widget_position:
                return

            tree_x, tree_y = widget_position

            # Track which image we're hovering over
            if self._current_hovered_image != image:
                self._current_hovered_image = image

            # Show the preview
            self._show_preview(image.pixbuf_data, tree_x, tree_y)

    def _on_tree_leave(self, controller):
        """Handle mouse leaving the tree view"""
        image = controller.get_widget()
        if image == self._current_hovered_image:
            self._hide_preview()

    def _show_preview(self, pixbuf, x, y):
        """Show a preview of the album art at the cursor position"""
        # Create popover if it doesn't exist
        if not self.last_preview_popover:
            self.last_preview_popover = Gtk.Popover()
            self.last_preview_popover.set_autohide(True)

            # Create an image widget for the preview
            self.preview_image = Gtk.Image()
            self.preview_image.set_size_request(200, 200)

            # Add the image to the popover
            self.last_preview_popover.set_child(self.preview_image)
            self.last_preview_popover.set_parent(self.artists_tree)

        # Set the pixbuf to the image widget
        self.preview_image.set_from_pixbuf(pixbuf)

        # Position the popover near the cursor but offset to prevent it from hiding the cell
        rect = Gdk.Rectangle()
        rect.x = int(x) + 20  # Offset from cursor
        rect.y = int(y)
        rect.width = 1
        rect.height = 1

        self.last_preview_popover.set_pointing_to(rect)
        self.last_preview_popover.popup()

    def _hide_preview(self):
        """Hide the album art preview popover"""
        self._current_hovered_image = None
        if self.last_preview_popover:
            self.last_preview_popover.popdown()

    def _on_right_click(self, gesture, n_press, x, y, list_item):
        """Handle right-click on items"""
        tree_list_row = list_item.tree_list_row
        if not tree_list_row:
            return

        item = tree_list_row.get_item()
        if not item:
            return

        # Create appropriate menu items
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
            list_item.get_child(),  # Parent widget
            menu_items,  # Menu items
            "row",  # Action group name
            x,  # X position
            y,  # Y position
        )

    def _on_context_menu_action(self, item, replace):
        """Handle context menu actions"""
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
        """Play all songs by an artist"""
        try:
            # Clear current playlist if replacing
            if replace:
                await self.mpd_client.async_clear_playlist()

            # Find and add all songs by the artist
            songs = await self.mpd_client.async_get_songs_by_artist(artist_name)
            if songs:
                await self.mpd_client.async_add_songs_to_playlist(
                    [song["file"] for song in songs]
                )

                # Start playback if we replaced the playlist
                if replace:
                    self.mpd_client.client.play(0)
        except Exception as e:
            print(f"Error playing artist songs: {e}")

    async def _play_album_songs(self, album, replace=True):
        """Play all songs from an album"""
        try:
            # Clear current playlist if replacing
            if replace:
                await self.mpd_client.async_clear_playlist()

            # Find and add all songs from the album
            songs = await self.mpd_client.async_find(
                "artist", album.artist, "album", album.title
            )
            if songs:
                # Sort by track number if possible
                songs.sort(
                    key=lambda song: (
                        int(song["track"].split("/")[0])
                        if "track" in song and song["track"].split("/")[0].isdigit()
                        else 9999
                    )
                )

                await self.mpd_client.async_add_songs_to_playlist(
                    [song["file"] for song in songs]
                )

                # Start playback if we replaced the playlist
                if replace:
                    self.mpd_client.client.play(0)
        except Exception as e:
            print(f"Error playing album songs: {e}")

    async def _play_song(self, file_path, replace=True):
        """Play a single song"""
        try:
            # Clear current playlist if replacing
            if replace:
                await self.mpd_client.async_clear_playlist()

            # Add song to playlist
            await self.mpd_client.async_add_songs_to_playlist([file_path])

            # Start playback
            self.mpd_client.client.play(0 if replace else -1)
        except Exception as e:
            print(f"Error playing song: {e}")

    async def load_artists(self):
        """Load all artists from MPD"""
        if not self.mpd_client.is_connected():
            return False

        try:
            # Clear current items
            self.artists_store.remove_all()

            # Get all artists
            artists = await self.mpd_client.async_get_artists()
            if artists:
                # Sort artists alphabetically using custom sorting
                artists.sort(key=lambda artist_name: get_sort_key(artist_name))

                # Add artist items to store
                for artist_name in artists:
                    if artist_name:  # Skip empty artist names
                        artist = Artist(artist_name)
                        self.artists_store.append(artist)

            # Force UI update
            GLib.idle_add(lambda: self.artists_tree.queue_draw())
        except Exception as e:
            print(f"Error loading artists: {e}")

        return False

    def refresh(self):
        """Refresh the artists view"""
        AsyncUIHelper.run_async_operation(self.load_artists, None)
