from typing import Any
from gi.repository import GObject


class Artist(GObject.GObject):
    """GObject wrapper for artist data"""

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.albums = []
        self.children_loaded = False
        self.list_item = None


class Album(GObject.GObject):
    """GObject wrapper for album data"""

    def __init__(self, title, artist=None, icon_name=None, pixbuf=None):
        super().__init__()
        self.title = title
        self.artist = artist
        self.icon_name = icon_name
        self.pixbuf = pixbuf
        self.year = None
        self.songs = []
        self.songs_loaded = False
        self.list_item = None
        self.children_model: Any | None = None


class Song(GObject.GObject):
    """GObject wrapper for song data"""

    def __init__(self, **data):
        super().__init__()
        self.id = None
        self.artist = None
        self.album = None
        self.track = None
        self.file = "Unknown"
        self.title = None
        self.list_item = None

        for i in data:
            setattr(self, i, data[i])

    def get(self, key, default=None):
        """Return the named field, unwrapping list-valued MPD tags.

        MPD returns fields like ``artist`` when multiple values are set as
        a list; this returns the first element so callers don't have to
        special-case that.
        """
        value = getattr(self, key, None)
        if isinstance(value, list):
            return value[0] if value else default
        if value is None:
            return default
        return value

    def get_title(self):
        """Return the song's title, falling back to the file path."""
        return self.get("title") or self.get("file", "Unknown")


class FileItem(GObject.GObject):
    """A file item for the file tree view"""

    def __init__(self, name, path, icon_name, is_directory, pixbuf=None):
        super().__init__()
        self.name = name
        self.path = path
        self.icon_name = icon_name
        self.is_directory = is_directory
        self.pixbuf = pixbuf
        self.list_item = None
        self.children = []
        self.children_loaded = False
