from galliard.models import Album, Artist, FileItem, Song


class TestSong:
    def test_get_returns_attribute(self):
        song = Song(title="Hello", artist="World")
        assert song.get("title") == "Hello"
        assert song.get("artist") == "World"

    def test_get_unwraps_list_valued_tag(self):
        # MPD returns multi-valued tags as a Python list.
        song = Song(artist=["Alice", "Bob"])
        assert song.get("artist") == "Alice"

    def test_get_unwraps_empty_list_to_default(self):
        song = Song(artist=[])
        assert song.get("artist", "fallback") == "fallback"

    def test_get_missing_returns_default(self):
        song = Song()
        assert song.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_without_default_returns_none(self):
        song = Song()
        assert song.get("nonexistent") is None

    def test_get_title_falls_back_to_file(self):
        song = Song(file="music/track.mp3")
        assert song.get_title() == "music/track.mp3"

    def test_get_title_prefers_title(self):
        song = Song(title="Song Name", file="music/track.mp3")
        assert song.get_title() == "Song Name"

    def test_get_title_final_fallback(self):
        # No title, no file -> returns the default "Unknown".
        song = Song()
        song.file = None
        assert song.get_title() == "Unknown"

    def test_constructor_sets_arbitrary_fields(self):
        song = Song(title="T", artist="A", album="Al", track="5", date="2024")
        assert song.title == "T"
        assert song.artist == "A"
        assert song.album == "Al"
        assert song.track == "5"
        assert song.date == "2024"

    def test_subscript_raises_after_shim_removal(self):
        # The __getitem__ shim was deliberately removed in phase 1b;
        # dict-style access must fail loudly.
        song = Song(title="T")
        try:
            _ = song["title"]
        except TypeError:
            return
        raise AssertionError("Song.__getitem__ should no longer exist")


class TestAlbum:
    def test_construction(self):
        album = Album(title="OK Computer", artist="Radiohead")
        assert album.title == "OK Computer"
        assert album.artist == "Radiohead"
        assert album.songs == []
        assert album.songs_loaded is False

    def test_construction_with_defaults(self):
        album = Album(title="x")
        assert album.artist is None
        assert album.icon_name is None
        assert album.pixbuf is None


class TestArtist:
    def test_construction(self):
        artist = Artist("Radiohead")
        assert artist.name == "Radiohead"
        assert artist.albums == []
        assert artist.children_loaded is False


class TestFileItem:
    def test_directory(self):
        item = FileItem(
            name="Music",
            path="Music",
            icon_name="folder-symbolic",
            is_directory=True,
        )
        assert item.is_directory is True
        assert item.children == []

    def test_file(self):
        item = FileItem(
            name="a.mp3",
            path="Music/a.mp3",
            icon_name="audio-x-generic-symbolic",
            is_directory=False,
        )
        assert item.is_directory is False
