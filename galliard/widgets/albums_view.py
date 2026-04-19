import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio  # noqa: E402

from galliard.models import Album  # noqa: E402
from galliard.utils.sorting import get_sort_key  # noqa: E402
from galliard.utils.album_art import get_album_art_as_pixbuf  # noqa: E402
from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402


class AlbumsView(Gtk.ScrolledWindow):
    """Flat album list for the library sidebar (cover + title + artist + play)."""

    def __init__(self, mpd_client):
        """Build the scrolled list view; call :meth:`load_albums` to populate."""
        super().__init__()
        self.mpd_client = mpd_client

        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.create_ui()

    def create_ui(self):
        """Create the underlying Gio.ListStore and Gtk.ListView."""
        self.albums_store = Gio.ListStore(item_type=Album)

        self.albums_list = Gtk.ListView.new(
            Gtk.NoSelection.new(self.albums_store), self.create_album_factory()
        )

        self.set_child(self.albums_list)

    def create_album_factory(self):
        """Build the SignalListItemFactory wiring setup/bind to our handlers."""
        factory = Gtk.SignalListItemFactory.new()
        factory.connect("setup", self._album_item_setup)
        factory.connect("bind", self._album_item_bind)
        return factory

    def _album_item_setup(self, factory, list_item):
        """Construct an album row: cover | title+artist | play."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        cover = Gtk.Image()
        cover.set_size_request(48, 48)
        cover.set_from_icon_name("media-optical-symbolic")
        box.append(cover)

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

        play_button = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        play_button.add_css_class("flat")
        play_button.set_tooltip_text("Play this album")
        play_button.connect("clicked", self._on_album_play_clicked, list_item)
        box.append(play_button)

        list_item.set_child(box)
        list_item.cover = cover
        list_item.title_label = title_label
        list_item.artist_label = artist_label

    def _album_item_bind(self, factory, list_item):
        """Populate a recycled row from the Album at its position."""
        album = list_item.get_item()
        if album:
            list_item.title_label.set_text(album.title)

            AsyncUIHelper.run_async_operation(
                self._load_album_art,
                lambda result, item=list_item: self._update_album_art(item, result),
                album.title,
            )

            if hasattr(album, "artist") and album.artist:
                list_item.artist_label.set_text(album.artist)
                list_item.artist_label.set_visible(True)
            else:
                list_item.artist_label.set_visible(False)

    async def _load_album_art(self, album_name):
        """Fetch album art via the first song of ``album_name``."""
        try:
            songs = await self.mpd_client.async_get_songs_by_album(album_name)
            if songs:
                return await get_album_art_as_pixbuf(
                    self.mpd_client, songs[0].file, 48
                )
        except Exception as e:
            print(f"Error loading album art: {e}")
        return None

    def _update_album_art(self, list_item, pixbuf):
        """Drop the fetched pixbuf onto the row's cover image."""
        if list_item and pixbuf:
            list_item.cover.set_from_pixbuf(pixbuf)

    def _on_album_play_clicked(self, button, list_item):
        """Per-row play button: replace the playlist with the album's songs."""
        album = list_item.get_item()
        if album and self.mpd_client.is_connected():
            AsyncUIHelper.run_async_operation(self._play_album_songs, None, album.title)

    async def _play_album_songs(self, album_name):
        """Clear playlist, add all songs in ``album_name`` sorted by track, play."""
        try:
            await self.mpd_client.async_clear_playlist()

            songs = await self.mpd_client.async_get_songs_by_album(album_name)
            if not songs:
                return

            def track_sort_key(song):
                track = song.track
                if isinstance(track, list):
                    track = track[0] if track else None
                if not track:
                    return 0
                # Track tags can be "5/12"; take the leading number.
                first = str(track).split("/")[0]
                return int(first) if first.isdigit() else 0

            songs.sort(key=track_sort_key)

            await self.mpd_client.async_add_songs_to_playlist(
                [song.file for song in songs]
            )
            await self.mpd_client.async_play(0)
        except Exception as e:
            print(f"Error playing album songs: {e}")

    async def load_albums(self):
        """Refresh ``self.albums_store`` from MPD, sorted case/accent-insensitively."""
        if not self.mpd_client.is_connected():
            return

        albums = await self.mpd_client.async_get_albums()
        if albums:
            albums.sort(key=lambda album: get_sort_key(album.title))

            self.albums_store.remove_all()
            for album in albums:
                self.albums_store.append(album)

    def refresh(self):
        """Re-fetch and redisplay the album list."""
        AsyncUIHelper.run_async_operation(self.load_albums, None)
