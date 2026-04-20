"""Exercise the per-view ``_item_bind`` / signal handler paths.

Gated on ``@pytest.mark.gtk`` because they instantiate the widget
tree; skipped when Gtk4 or a display aren't available.
"""

from unittest.mock import MagicMock

import pytest

from galliard.models import Album, Artist, FileItem, Song


pytestmark = pytest.mark.gtk


@pytest.fixture(autouse=True)
def _no_async_dispatch(monkeypatch):
    """Neutralise the async task queue for widget tests.

    Bind callbacks routinely kick off art-loading or playlist-refresh
    tasks; we don't want those to fire (or need a running loop) during
    narrow widget tests.
    """
    from galliard.utils.async_task_queue import AsyncUIHelper

    monkeypatch.setattr(
        AsyncUIHelper, "run_async_operation",
        staticmethod(lambda *a, **kw: None),
    )
    monkeypatch.setattr(
        AsyncUIHelper, "run_glib_idle_async",
        staticmethod(lambda *a, **kw: None),
    )


# ---------------------------------------------------------------------------
# mpd_item_row.build_compact_tree_row
# ---------------------------------------------------------------------------

class TestBuildCompactTreeRow:
    def _fake_list_item(self):
        return MagicMock(spec=["set_child"])

    def test_minimal_row_has_expander_image_label(self, gtk_app):
        from galliard.widgets.mpd_item_row import build_compact_tree_row

        item = self._fake_list_item()
        build_compact_tree_row(item)

        assert item.expander is not None
        assert item.image is not None
        assert item.label is not None
        assert not hasattr(item, "play_button")

    def test_play_button_added_when_callback_given(self, gtk_app):
        from galliard.widgets.mpd_item_row import build_compact_tree_row

        item = self._fake_list_item()
        on_play = MagicMock()
        build_compact_tree_row(item, on_play=on_play)
        assert hasattr(item, "play_button")
        # Click connection wires the callback.
        item.play_button.emit("clicked")
        on_play.assert_called()

    def test_expander_click_invokes_callback(self, gtk_app):
        from galliard.widgets.mpd_item_row import build_compact_tree_row

        item = self._fake_list_item()
        on_expand = MagicMock()
        build_compact_tree_row(item, on_expand=on_expand)
        item.expander.emit("clicked")
        on_expand.assert_called()


# ---------------------------------------------------------------------------
# albums_view._album_item_bind
# ---------------------------------------------------------------------------

@pytest.fixture
def albums_view(gtk_app):
    from galliard.widgets.albums_view import AlbumsView

    return AlbumsView(gtk_app.mpd_conn)


class TestAlbumsView:
    def test_bind_sets_title_label(self, albums_view, gtk_app):
        # Pretend a scroll has laid out this row with an Album.
        album = Album(title="OK Computer", artist="Radiohead")
        list_item = MagicMock()
        list_item.get_item.return_value = album

        # Attach the child widgets the bind function writes to.
        list_item.title_label = MagicMock()
        list_item.artist_label = MagicMock()
        list_item.cover = MagicMock()

        albums_view._album_item_bind(None, list_item)
        list_item.title_label.set_text.assert_called_with("OK Computer")
        list_item.artist_label.set_text.assert_called_with("Radiohead")
        list_item.artist_label.set_visible.assert_called_with(True)

    def test_bind_hides_artist_label_when_missing(self, albums_view):
        album = Album(title="Mystery")  # no artist
        list_item = MagicMock()
        list_item.get_item.return_value = album
        list_item.title_label = MagicMock()
        list_item.artist_label = MagicMock()
        list_item.cover = MagicMock()

        albums_view._album_item_bind(None, list_item)
        list_item.artist_label.set_visible.assert_called_with(False)

    def test_update_album_art_sets_pixbuf(self, albums_view):
        list_item = MagicMock()
        list_item.cover = MagicMock()
        pixbuf = MagicMock()
        albums_view._update_album_art(list_item, pixbuf)
        list_item.cover.set_from_pixbuf.assert_called_with(pixbuf)

    def test_update_album_art_noop_when_no_pixbuf(self, albums_view):
        list_item = MagicMock()
        list_item.cover = MagicMock()
        albums_view._update_album_art(list_item, None)
        list_item.cover.set_from_pixbuf.assert_not_called()


# ---------------------------------------------------------------------------
# artists_view._item_bind
# ---------------------------------------------------------------------------

@pytest.fixture
def artists_view(gtk_app):
    from galliard.widgets.artists_view import ArtistsView

    return ArtistsView(gtk_app.mpd_conn)


def _tree_row(item, depth=0, expanded=False):
    """Build a fake TreeListRow wrapping ``item``."""
    row = MagicMock()
    row.get_item.return_value = item
    row.get_depth.return_value = depth
    row.get_expanded.return_value = expanded
    return row


def _list_item(tree_row):
    """Build a fake list_item for a tree view."""
    list_item = MagicMock()
    list_item.get_item.return_value = tree_row
    list_item.expander = MagicMock()
    list_item.image = MagicMock()
    list_item.label = MagicMock()
    list_item.play_button = MagicMock()
    return list_item


class TestArtistsViewBind:
    def test_artist_row_shows_performer_icon(self, artists_view):
        artist = Artist("Radiohead")
        list_item = _list_item(_tree_row(artist))
        artists_view._item_bind(None, list_item)
        list_item.image.set_from_icon_name.assert_called_with("avatar-default-symbolic")
        list_item.label.set_text.assert_called_with("Radiohead")
        # Artists are expandable -> expander + play button visible.
        list_item.expander.set_visible.assert_called_with(True)
        list_item.play_button.set_visible.assert_called_with(True)

    def test_album_row_with_pixbuf(self, artists_view):
        album = Album(title="In Rainbows", artist="Radiohead")
        album.pixbuf = MagicMock()
        list_item = _list_item(_tree_row(album, depth=1))
        artists_view._item_bind(None, list_item)
        list_item.image.set_from_pixbuf.assert_called_with(album.pixbuf)
        list_item.label.set_text.assert_called_with("In Rainbows")

    def test_album_row_without_pixbuf_uses_optical_icon(self, artists_view):
        album = Album(title="Kid A", artist="Radiohead")
        list_item = _list_item(_tree_row(album, depth=1))
        artists_view._item_bind(None, list_item)
        list_item.image.set_from_icon_name.assert_called_with(
            "media-optical-symbolic"
        )

    def test_album_row_shows_year_when_present(self, artists_view):
        album = Album(title="In Rainbows", artist="Radiohead")
        album.year = 2007
        list_item = _list_item(_tree_row(album, depth=1))
        artists_view._item_bind(None, list_item)
        list_item.label.set_text.assert_called_with("In Rainbows (2007)")

    def test_song_row_hides_expander_and_play(self, artists_view):
        song = Song(title="Nude", track="5", file="a.mp3")
        list_item = _list_item(_tree_row(song, depth=2))
        artists_view._item_bind(None, list_item)
        list_item.expander.set_visible.assert_called_with(False)
        list_item.play_button.set_visible.assert_called_with(False)
        # Track number is prefixed onto the title.
        list_item.label.set_text.assert_called_with("5. Nude")


class TestArtistsViewChildrenModels:
    def test_artist_children_model_returns_store_with_loading_placeholder(
        self, artists_view
    ):
        artist = Artist("Radiohead")
        model = artists_view._create_artist_children_model(artist)
        # A single "Loading..." placeholder while the fetch is in flight.
        assert model.get_n_items() == 1

    def test_artist_children_model_returns_existing_albums_if_loaded(
        self, artists_view
    ):
        artist = Artist("Radiohead")
        artist.children_loaded = True
        artist.albums = [
            Album(title="A"),
            Album(title="B"),
        ]
        model = artists_view._create_artist_children_model(artist)
        assert model.get_n_items() == 2

    def test_album_children_model_sorts_by_track(self, artists_view):
        album = Album(title="X")
        album.songs = [
            Song(file="c.mp3", title="Three", track="3"),
            Song(file="a.mp3", title="One", track="1"),
            Song(file="b.mp3", title="Two", track="2"),
        ]
        model = artists_view._create_album_children_model(album)
        assert model.get_n_items() == 3
        first = model.get_item(0)
        assert first.title == "One"

    def test_children_dispatcher_handles_both_types(self, artists_view):
        assert artists_view._create_children_model(Artist("A")) is not None
        assert artists_view._create_children_model(Album(title="A")) is not None
        assert artists_view._create_children_model(Song(file="a.mp3")) is None

    def test_album_children_model_sorts_by_year_then_title(self, artists_view):
        """Loaded albums are ordered (year, title), unknown year last."""
        a = Album(title="Later")
        a.year = 2001
        b = Album(title="Earlier")
        b.year = 1999
        c = Album(title="No Year")  # year stays None -> sorts last
        d = Album(title="Also 2001")
        d.year = 2001
        artist = Artist("X")
        artist.children_loaded = True
        artist.albums = [a, c, b, d]
        model = artists_view._create_artist_children_model(artist)
        titles = [model.get_item(i).title for i in range(model.get_n_items())]
        # 1999 first, then 2001 albums alphabetically, then year-less.
        assert titles == ["Earlier", "Also 2001", "Later", "No Year"]


class TestArtistAlbumOwnership:
    """Albums discovered via albumartist are owned; artist-only are guests."""

    async def test_owned_album_marked(self, artists_view):
        from unittest.mock import AsyncMock

        artists_view.mpd_client = AsyncMock()
        artists_view.mpd_client.async_get_albums_by_albumartist.return_value = [
            Album(title="Home Turf", artist="Wombat Philharmonic"),
        ]
        artists_view.mpd_client.async_get_albums_by_artist.return_value = []

        albums = await artists_view._load_artist_albums(["Wombat Philharmonic"])
        assert len(albums) == 1
        assert albums[0].is_owned is True

    async def test_guest_only_album_marked_not_owned(self, artists_view):
        from unittest.mock import AsyncMock

        artists_view.mpd_client = AsyncMock()
        artists_view.mpd_client.async_get_albums_by_albumartist.return_value = []
        artists_view.mpd_client.async_get_albums_by_artist.return_value = [
            Album(title="Compilation", artist="Dancing Potatoes"),
        ]

        albums = await artists_view._load_artist_albums(["Dancing Potatoes"])
        assert len(albums) == 1
        assert albums[0].is_owned is False

    async def test_album_present_under_both_lists_is_owned(self, artists_view):
        from unittest.mock import AsyncMock

        artists_view.mpd_client = AsyncMock()
        artists_view.mpd_client.async_get_albums_by_albumartist.return_value = [
            Album(title="Self Title", artist="Quantum Ferrets"),
        ]
        artists_view.mpd_client.async_get_albums_by_artist.return_value = [
            Album(title="Self Title", artist="Quantum Ferrets"),
        ]

        albums = await artists_view._load_artist_albums(["Quantum Ferrets"])
        assert len(albums) == 1
        assert albums[0].is_owned is True


# ---------------------------------------------------------------------------
# files_view._file_item_bind
# ---------------------------------------------------------------------------

@pytest.fixture
def files_view(gtk_app):
    from galliard.widgets.files_view import FilesView

    return FilesView(gtk_app.mpd_conn)


class TestFilesViewBind:
    def test_directory_row_shows_expander(self, files_view):
        item = FileItem(
            name="Albums", path="Albums",
            icon_name="folder-symbolic", is_directory=True,
        )
        list_item = _list_item(_tree_row(item))
        files_view._file_item_bind(None, list_item)
        list_item.expander.set_visible.assert_called_with(True)
        list_item.label.set_text.assert_called_with("Albums")
        list_item.image.set_from_icon_name.assert_called_with("folder-symbolic")

    def test_file_row_hides_expander(self, files_view):
        item = FileItem(
            name="a.mp3", path="Albums/a.mp3",
            icon_name="audio-x-generic-symbolic", is_directory=False,
        )
        list_item = _list_item(_tree_row(item))
        files_view._file_item_bind(None, list_item)
        list_item.expander.set_visible.assert_called_with(False)

    def test_is_music_file_recognises_common_extensions(self, files_view):
        assert files_view._is_music_file("a/b/c.mp3") is True
        assert files_view._is_music_file("song.FLAC") is True
        assert files_view._is_music_file("track.opus") is False  # not in list
        assert files_view._is_music_file("track.m4a") is True
        assert files_view._is_music_file("cover.jpg") is False


# ---------------------------------------------------------------------------
# search_results_view create_title_file_item / apply_art
# ---------------------------------------------------------------------------

@pytest.fixture
def search_view(gtk_app, monkeypatch):
    from galliard.widgets.search_results_view import SearchResultsView
    import galliard.widgets.search_results_view as search_module

    # Stub fetch_art_async so constructing title items doesn't queue work.
    monkeypatch.setattr(search_module, "fetch_art_async", lambda *a, **kw: None)
    return SearchResultsView(gtk_app.mpd_conn)


class TestSearchResultsViewHelpers:
    def test_create_title_file_item_formats_name(self, search_view):
        song = Song(
            file="a.mp3", title="Song", artist="Artist", album="Album",
            track="3",
        )
        item = search_view._create_title_file_item(song)
        assert "3. Song" in item.name
        assert "Artist" in item.name
        assert "Album" in item.name
        assert item.path == "a.mp3"

    def test_apply_art_to_item_stores_pixbuf(self, search_view):
        pixbuf = MagicMock()
        file_item = FileItem(
            name="x", path="", icon_name="...", is_directory=False,
        )
        search_view._apply_art_to_item(file_item, pixbuf)
        assert file_item.pixbuf is pixbuf
        assert file_item.icon_name is None

    def test_apply_art_noop_when_pixbuf_is_none(self, search_view):
        file_item = FileItem(
            name="x", path="", icon_name="keep-me", is_directory=False,
        )
        search_view._apply_art_to_item(file_item, None)
        assert file_item.pixbuf is None
        assert file_item.icon_name == "keep-me"


# ---------------------------------------------------------------------------
# player_controls signal handlers
# ---------------------------------------------------------------------------

@pytest.fixture
def player_controls(gtk_app):
    from galliard.widgets.player_controls import PlayerControls

    return PlayerControls(gtk_app.mpd_conn)


class TestPlayerControlsSignalHandlers:
    def test_format_time(self, player_controls):
        assert player_controls.format_time(65) == "1:05"
        assert player_controls.format_time(3661) == "61:01"
        assert player_controls.format_time(0) == "0:00"

    def test_on_song_changed_with_current_song(self, player_controls, gtk_app):
        gtk_app.mpd_conn.connected = True
        gtk_app.mpd_conn.current_song = Song(
            title="Creep", artist="Radiohead", album="Pablo Honey",
            file="a.mp3",
        )
        player_controls.on_song_changed(gtk_app.mpd_conn)
        assert "Creep" in player_controls.song_title_label.get_text()
        assert "Radiohead" in player_controls.song_artist_label.get_text()

    def test_on_song_changed_no_song_clears_labels(self, player_controls, gtk_app):
        gtk_app.mpd_conn.connected = False
        gtk_app.mpd_conn.current_song = None
        player_controls.on_song_changed(gtk_app.mpd_conn)
        assert player_controls.song_title_label.get_text() == "Not playing"

    def test_on_repeat_changed_repeat_and_single(self, player_controls):
        player_controls.on_repeat_changed(None, True, True)
        assert player_controls.repeat_button.get_icon_name() == (
            "media-playlist-repeat-song-symbolic"
        )

    def test_on_repeat_changed_repeat_only(self, player_controls):
        player_controls.on_repeat_changed(None, True, False)
        assert player_controls.repeat_button.get_icon_name() == (
            "media-playlist-repeat-symbolic"
        )

    def test_on_random_changed_on(self, player_controls):
        player_controls.on_random_changed(None, True)
        assert player_controls.random_button.get_icon_name() == (
            "media-playlist-shuffle-symbolic"
        )

    def test_on_random_changed_off(self, player_controls):
        player_controls.on_random_changed(None, False)
        assert player_controls.random_button.get_icon_name() == (
            "media-playlist-consecutive-symbolic"
        )

    def test_update_volume_lines_activates_proportionally(self, player_controls):
        """At 50% volume, half the line widgets should have the active class."""
        player_controls.mpd_client.connected = True
        total = len(player_controls.volume_lines)
        player_controls.update_volume_lines(50)
        active = sum(
            1
            for line in player_controls.volume_lines
            if "volume-line" in line.get_css_classes()
            and "volume-line-inactive" not in line.get_css_classes()
        )
        # Allow a rounding error of 1.
        assert abs(active - total // 2) <= 1


# ---------------------------------------------------------------------------
# playlist_view._bind_song_data_to_row
# ---------------------------------------------------------------------------

@pytest.fixture
def playlist_view(gtk_app):
    from galliard.widgets.playlist_view import PlaylistView

    return PlaylistView(gtk_app.mpd_conn)


class TestPlaylistViewBind:
    def test_bind_sets_title_and_subtitle(self, playlist_view):
        row = MagicMock()
        row.album_art = MagicMock()
        row.playing_icon = MagicMock()
        row.number_label = MagicMock()
        # getattr(row, "album_art") / .playing_icon / .number_label need the
        # attributes configured; MagicMock satisfies this.

        song = Song(
            file="a.mp3", title="Creep", artist="Radiohead",
            album="Pablo Honey", id=42,
        )
        playlist_view._bind_song_data_to_row(row, song, position=0)
        row.set_title.assert_called()
        row.set_subtitle.assert_called()
        title = row.set_title.call_args[0][0]
        assert "Creep" in title
