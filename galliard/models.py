from gi.repository import GObject


class Artist(GObject.GObject):
    """GObject wrapper for artist data"""

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.albums = []
        self.children_loaded = False


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


class Song(GObject.GObject):
    """GObject wrapper for song data"""

    def __init__(self, data):
        super().__init__()
        self.data = data

    def get_title(self):
        return self.data.get("title", self.data.get("file", "Unknown"))

    def get_artist(self):
        return self.data.get("artist", "Unknown")

    def get_album(self):
        return self.data.get("album", "")

    def get_file(self):
        return self.data.get("file", "")

    def get_id(self):
        return self.data.get("id")

    def get_pos(self):
        return self.data.get("pos")


class FileItem(GObject.Object):
    """A file item for the file tree view"""

    __gtype_name__ = "FileItem"

    def __init__(self, name, path, icon_name, is_directory, pixbuf=None):
        GObject.Object.__init__(self)
        self._name = name
        self._path = path
        self._icon_name = icon_name
        self._is_directory = is_directory
        self._pixbuf = pixbuf
        self._list_item = None
        self.children = []
        self.children_loaded = False

    @GObject.Property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @GObject.Property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value

    @GObject.Property
    def icon_name(self):
        return self._icon_name

    @icon_name.setter
    def icon_name(self, value):
        self._icon_name = value

    @GObject.Property
    def is_directory(self):
        return self._is_directory

    @is_directory.setter
    def is_directory(self, value):
        self._is_directory = value

    @GObject.Property
    def pixbuf(self):
        return self._pixbuf

    @pixbuf.setter
    def pixbuf(self, value):
        self._pixbuf = value

    @GObject.Property
    def list_item(self):
        return self._list_item

    @list_item.setter
    def list_item(self, value):
        self._list_item = value
