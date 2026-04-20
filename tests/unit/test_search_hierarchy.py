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

    def test_song_appears_under_both_artist_and_albumartist(self, search_view):
        """Featured tracks show under the guest *and* the album owner."""
        songs = [
            _song(
                file="a",
                artist="Featured Alice",
                albumartist="Main Artist",
                album="A",
            ),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="")
        names = sorted(a.name for a in artists)
        assert names == ["Featured Alice", "Main Artist"]

    def test_slash_joined_artists_split_into_separate_rows(self, search_view):
        """"Alpha / Beta" produces both an "Alpha" and a "Beta" row."""
        songs = [
            _song(file="a", artist="Alpha / Beta", album="X", title="1"),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="")
        names = sorted(a.name for a in artists)
        assert names == ["Alpha", "Beta"]

    def test_case_variant_artists_merge_into_one_row(self, search_view):
        songs = [
            _song(file="a", artist="Alpha", album="X", title="1"),
            _song(file="b", artist="alpha", album="X", title="2"),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="")
        assert len(artists) == 1
        assert artists[0].name == "Alpha"

    def test_compound_artist_songs_appear_under_each_part(self, search_view):
        """The same song shows up under every split artist, once per row."""
        songs = [
            _song(file="a", artist="Alpha / Beta", album="X", title="1"),
            _song(file="b", artist="Alpha", album="Y", title="2"),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="")
        by_name = {a.name: a for a in artists}
        # "Alpha" row: albums X (from compound) and Y (from solo).
        alpha_albums = sorted(al.name for al in by_name["Alpha"].children)
        assert alpha_albums == ["X", "Y"]
        # "Beta" row: only the compound-tagged album.
        beta_albums = [al.name for al in by_name["Beta"].children]
        assert beta_albums == ["X"]

    def test_filter_to_search_drops_irrelevant_split_parts(self, search_view):
        """Searching for "steven" shouldn't surface the "Chris" half of a split tag."""
        songs = [
            _song(file="a", artist="Chris / Steven Curtis", album="X", title="1"),
            _song(file="b", artist="Steven Anderson", album="Y", title="2"),
        ]
        artists = search_view._build_artist_hierarchy(
            songs, search_term="steven", filter_to_search=True,
        )
        names = sorted(a.name for a in artists)
        assert names == ["Steven Anderson", "Steven Curtis"]

    def test_filter_to_search_is_case_insensitive(self, search_view):
        songs = [
            _song(file="a", artist="STEVEN ANDERSON", album="X", title="1"),
        ]
        artists = search_view._build_artist_hierarchy(
            songs, search_term="steven", filter_to_search=True,
        )
        assert len(artists) == 1
        assert artists[0].name == "STEVEN ANDERSON"

    def test_filter_to_search_off_by_default(self, search_view):
        """Date-hierarchy callers get un-filtered artist rows."""
        songs = [
            _song(file="a", artist="Alpha / Beta", album="X", title="1"),
        ]
        artists = search_view._build_artist_hierarchy(songs, search_term="alpha")
        names = sorted(a.name for a in artists)
        assert names == ["Alpha", "Beta"]

    def test_compound_track_on_headlined_album_surfaces_under_featured(
        self, search_view
    ):
        """Guest-track regression: searching for the featured artist must
        still surface the track even when the album's albumartist is a
        different artist whose display row got filtered out.
        """
        songs = [
            _song(
                file="a",
                artist="The Wombat Philharmonic / Dancing Potatoes",
                albumartist="The Wombat Philharmonic",
                album="Live at the Burrow",
                title="Spud Waltz",
            ),
        ]
        artists = search_view._build_artist_hierarchy(
            songs, search_term="potato", filter_to_search=True,
        )
        names = [a.name for a in artists]
        assert names == ["Dancing Potatoes"]
        albums = artists[0].children
        assert [al.name for al in albums] == ["Live at the Burrow"]


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
