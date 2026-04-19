"""The ``_build_*_hierarchy`` methods on SearchResultsView.

These construct FileItem trees from raw Song lists. The non-obvious
pieces are:
  - ``_build_album_hierarchy`` groups by ``(album, artist, year)``, not
    by album name alone, so reissues / same-name-different-artist albums
    stay separate.
  - Sort order is year -> album-name -> artist.
"""

import pytest

from galliard.models import Song


@pytest.fixture
def search_view(monkeypatch):
    """A SearchResultsView without the Gtk widgets set up.

    We only need the pure-Python hierarchy-building methods; bypassing
    ``__init__`` avoids pulling in the whole widget tree.
    """
    from galliard.widgets.search_results_view import SearchResultsView

    view = SearchResultsView.__new__(SearchResultsView)
    view.counter = 0
    view.mpd_conn = None  # fetch_art_async is stubbed, so no real client needed
    # _create_album_file_item runs fetch_art_async; patch it to a no-op
    # so the hierarchy builders can run without AsyncUIHelper wired up.
    import galliard.widgets.search_results_view as search_module

    monkeypatch.setattr(
        search_module, "fetch_art_async",
        lambda *a, **kw: None,
    )
    return view


def _song(**fields):
    return Song(**fields)


class TestAlbumHierarchy:
    def test_groups_by_album_name(self, search_view):
        songs = [
            _song(file="a", album="X", artist="A", title="1"),
            _song(file="b", album="X", artist="A", title="2"),
        ]
        albums = search_view._build_album_hierarchy(songs, search_term="x")
        assert len(albums) == 1
        assert albums[0].name == "X"
        assert len(albums[0].children) == 2

    def test_same_name_different_artists_stay_separate(self, search_view):
        songs = [
            _song(file="a", album="Greatest Hits", artist="Alice", title="1"),
            _song(file="b", album="Greatest Hits", artist="Bob", title="2"),
        ]
        albums = search_view._build_album_hierarchy(songs, search_term="hits")
        # Two distinct rows even though both are titled "Greatest Hits".
        assert len(albums) == 2

    def test_same_album_different_years_stay_separate(self, search_view):
        """Reissues should not collapse with the original."""
        songs = [
            _song(file="a", album="Kind of Blue", artist="Miles", date="1959"),
            _song(file="b", album="Kind of Blue", artist="Miles", date="1997"),
        ]
        albums = search_view._build_album_hierarchy(songs, search_term="blue")
        assert len(albums) == 2

    def test_sorted_by_year_then_name(self, search_view):
        songs = [
            _song(file="a", album="Z", artist="A", date="2020"),
            _song(file="b", album="A", artist="A", date="1999"),
            _song(file="c", album="M", artist="A", date="2020"),
        ]
        albums = search_view._build_album_hierarchy(songs, search_term="")
        names = [a.name for a in albums]
        assert names == ["A", "M", "Z"]

    def test_albumartist_overrides_artist_for_keying(self, search_view):
        """Songs sharing an albumartist group together even when artists differ."""
        songs = [
            _song(
                file="a",
                album="Compilation",
                artist="Track Artist 1",
                albumartist="Various",
                date="2000",
            ),
            _song(
                file="b",
                album="Compilation",
                artist="Track Artist 2",
                albumartist="Various",
                date="2000",
            ),
        ]
        albums = search_view._build_album_hierarchy(songs, search_term="")
        assert len(albums) == 1


class TestArtistHierarchy:
    def test_groups_songs_by_artist(self, search_view):
        songs = [
            _song(file="a", artist="Alice", album="A", title="1"),
            _song(file="b", artist="Alice", album="A", title="2"),
            _song(file="c", artist="Bob", album="B", title="3"),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="")
        assert len(artists) == 2
        names = sorted(a.name for a in artists)
        assert names == ["Alice", "Bob"]

    def test_prefers_albumartist_over_artist(self, search_view):
        songs = [
            _song(
                file="a",
                artist="Featured Alice",
                albumartist="Main Artist",
                album="A",
            ),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="")
        assert artists[0].name == "Main Artist"


class TestDateHierarchy:
    def test_groups_by_year_descending(self, search_view):
        songs = [
            _song(file="a", date="1990", artist="A", album="A"),
            _song(file="b", date="2010", artist="B", album="B"),
            _song(file="c", date="2000", artist="C", album="C"),
        ]
        years = search_view._build_date_hierarchy(songs, search_term="")
        names = [y.name for y in years]
        assert names == ["2010", "2000", "1990"]
