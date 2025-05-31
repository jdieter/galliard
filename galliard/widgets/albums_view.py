import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio  # noqa: E402

from galliard.models import Album  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402


class AlbumsView(Gtk.ScrolledWindow):
    """Albums view for the library"""

    def __init__(self, mpd_client):
        super().__init__()
        self.mpd_client = mpd_client

        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # Create UI elements
        self.create_ui()

    def create_ui(self):
        """Create the albums view UI"""
        # Create list store with proper GType
        self.albums_store = Gio.ListStore(item_type=Album.__gtype__)

        # Create list view
        self.albums_list = Gtk.ListView.new(
            Gtk.NoSelection.new(self.albums_store), self.create_album_factory()
        )

        self.set_child(self.albums_list)

    def create_album_factory(self):
        """Create a factory for album list items"""
        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._album_item_setup)
        factory.connect("bind", self._album_item_bind)
        return factory

    def _album_item_setup(self, factory, list_item):
        """Setup function for album items"""
        # Create box for the row
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        # Album cover image
        cover = Gtk.Image()
        cover.set_size_request(48, 48)
        cover.set_from_icon_name("media-optical-symbolic")
        box.append(cover)

        # Album info box (title and artist)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info_box.set_hexpand(True)

        title_label = Gtk.Label()
        title_label.set_halign(Gtk.Align.START)
        title_label.add_css_class("heading")

        artist_label = Gtk.Label()
        artist_label.set_halign(Gtk.Align.START)
        artist_label.add_css_class("caption")

        info_box.append(title_label)
        info_box.append(artist_label)
        box.append(info_box)

        # Play button
        play_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        play_button.add_css_class("flat")
        play_button.set_tooltip_text("Play this album")
        play_button.connect("clicked", self._on_album_play_clicked, list_item)
        box.append(play_button)

        # Store references
        list_item.set_child(box)
        list_item.cover = cover
        list_item.title_label = title_label
        list_item.artist_label = artist_label

    def _album_item_bind(self, factory, list_item):
        """Bind album data to widget"""
        album = list_item.get_item()
        if album:
            list_item.title_label.set_text(album.name)

            # Load album art asynchronously
            AsyncUIHelper.run_async_operation(
                self._load_album_art,
                lambda result, item=list_item: self._update_album_art(item, result),
                album.name,
            )

            # If album has artist property, show it
            if hasattr(album, "artist") and album.artist:
                list_item.artist_label.set_text(album.artist)
                list_item.artist_label.set_visible(True)
            else:
                list_item.artist_label.set_visible(False)

    async def _load_album_art(self, album_name):
        """Load album art for an album"""
        try:
            # Find first song in this album
            songs = await self.mpd_client.async_get_songs_by_album(album_name)
            if songs:
                first_song = songs[0]
                return await get_album_art_as_pixbuf(
                    self.mpd_client, first_song["file"], 48
                )
        except Exception as e:
            print(f"Error loading album art: {e}")
        return None

    def _update_album_art(self, list_item, pixbuf):
        """Update album item with art"""
        if list_item and pixbuf:
            list_item.cover.set_from_pixbuf(pixbuf)

    def _on_album_play_clicked(self, button, list_item):
        """Handle album play button click"""
        album = list_item.get_item()
        if album and self.mpd_client.is_connected():
            # Play all songs in this album
            AsyncUIHelper.run_async_operation(self._play_album_songs, None, album.name)

    async def _play_album_songs(self, album_name):
        """Play all songs in an album"""
        try:
            # Clear current playlist
            await self.mpd_client.async_clear_playlist()

            # Find and add all songs in the album
            songs = await self.mpd_client.async_get_songs_by_album(album_name)
            if songs:
                # Sort by track number if available
                songs.sort(key=lambda song: int(song.get("track", "0").split("/")[0]))

                for song in songs:
                    self.mpd_client.add_to_playlist(song["file"])

                # Start playback
                self.mpd_client.client.play(0)
        except Exception as e:
            print(f"Error playing album songs: {e}")

    async def load_albums(self):
        """Load all albums from MPD"""
        if not self.mpd_client.is_connected():
            return

        albums = [item["album"] for item in await self.mpd_client.async_get_albums()]
        if albums:
            # Sort albums alphabetically using custom sorting
            albums.sort(key=lambda album: get_sort_key(album))

            # Update list store
            self.albums_store.remove_all()
            for album in albums:
                if album:  # Skip empty album names
                    self.albums_store.append(Album(album))

    async def load_albums_by_artist(self, artist):
        """Load albums by a specific artist"""
        if not self.mpd_client.is_connected():
            return

        albums = await self.mpd_client.async_get_album_by_artist(artist)
        if albums:
            # Sort using custom sorting
            albums.sort(key=lambda album: get_sort_key(album))

            # Update list store
            self.albums_store.remove_all()
            for album in albums:
                if album:  # Skip empty album names
                    album_data = Album(album)
                    album_data.artist = artist
                    self.albums_store.append(album_data)

    def refresh(self):
        """Refresh the albums view"""
        AsyncUIHelper.run_async_operation(self.load_albums, None)
