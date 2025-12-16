import logging
from collections import OrderedDict
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GdkPixbuf, Gdk, Gtk  # noqa: E402

_album_art_cache = OrderedDict()
_MAX_CACHE_SIZE = 2000  # Max number of cached album arts

async def get_album_art_as_pixbuf(mpd_conn, audio_file, size):
    """
    Get album art for a song and return it as a GdkPixbuf.Pixbuf

    Args:
        mpd_conn: The MPD client instance
        audio_file: Path to the audio file
        size: Desired size for the album art
    """
    if not mpd_conn.is_connected() or not audio_file:
        return None

    # Check cache first
    cache_location = mpd_conn.image_cache.get_image_path(audio_file)
    logging.debug(f"Cache location for {audio_file}: {cache_location}")
    if cache_location:
        cache_key = (cache_location, size)
        if cache_key in _album_art_cache:
            # Move to end (most recently used)
            _album_art_cache.move_to_end(cache_key)
            logging.debug(f"Album art cache hit for {audio_file} at size {size}")
            return _album_art_cache[cache_key]

    try:
        # Get album art data from MPD - await the async call
        binary_data, _, key = await mpd_conn.async_get_album_art(audio_file)
        logging.debug(f"Album art data length: {len(binary_data) if binary_data else 'None'}")
        if binary_data:
            # Create a PixbufLoader and load the image data directly
            loader = GdkPixbuf.PixbufLoader.new()

            # Write the binary data to the loader
            loader.write(binary_data)
            loader.close()

            # Get the pixbuf and scale it if necessary
            pixbuf = loader.get_pixbuf()
            if pixbuf:
                # Scale preserving aspect ratio
                width = pixbuf.get_width()
                height = pixbuf.get_height()
                if width > height:
                    new_width = size
                    new_height = int(height * (size / width))
                else:
                    new_height = size
                    new_width = int(width * (size / height))

                scaled_pixbuf = pixbuf.scale_simple(
                    new_width, new_height, GdkPixbuf.InterpType.BILINEAR
                )

                cache_key = (key, size)
                # Store in cache
                _album_art_cache[cache_key] = scaled_pixbuf
                _album_art_cache.move_to_end(cache_key)

                # Enforce cache size limit (remove oldest entry)
                if len(_album_art_cache) > _MAX_CACHE_SIZE:
                    _album_art_cache.popitem(last=False)

                logging.debug(f"Album art cached for {audio_file} at size {size} ({len(_album_art_cache)} items in cache)")
                return scaled_pixbuf
    except Exception as e:
        logging.info(f"Failed to get album art: {e}")

    return None


def apply_rounded_corners_to_picture(picture, radius=5):
    """
    Apply rounded corners to a Gtk.Picture widget using GTK4's overlay approach

    Args:
        picture: The Gtk.Picture widget
        radius: Corner radius in pixels
    """
    # Set up the style classes for rounded corners
    picture.set_overflow(Gtk.Overflow.HIDDEN)
    picture.add_css_class("rounded")

    # Apply CSS for rounded corners
    css_provider = Gtk.CssProvider()
    css = f"""
    .rounded {{
        border-radius: {radius}px;
    }}
    """
    css_provider.load_from_data(css.encode())

    # Apply the CSS to the widget
    if display := Gdk.Display.get_default():
        Gtk.StyleContext.add_provider_for_display(
            display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def get_default_icon_paintable(size):
    """
    Get the default icon paintable for missing album art

    Args:
        size: Desired size for the icon

    Returns:
        A Gtk.IconPaintable object
    """
    if display := Gdk.Display.get_default():
        return Gtk.IconTheme.get_for_display(display).lookup_icon(
            "audio-x-generic-symbolic",
            [],
            size,
            1,
            Gtk.TextDirection.NONE,
            Gtk.IconLookupFlags.FORCE_SYMBOLIC,
        )
    else:
        return None


def set_widget_album_art(image_widget, art_source, size=100, radius=8):
    """
    Set album art to a widget, handling different widget types

    Args:
        image_widget: Gtk.Picture or Gtk.Image widget
        art_source: Either a GdkPixbuf.Pixbuf or None for default icon
        size: Desired size for the art
        radius: Corner radius for Gtk.Picture widgets
    """
    is_picture = isinstance(image_widget, Gtk.Picture)

    if is_picture:
        # Configure Picture widget
        image_widget.set_size_request(size, size)
        apply_rounded_corners_to_picture(image_widget, radius=radius)

        if art_source:
            image_widget.set_paintable(Gdk.Texture.new_for_pixbuf(art_source))
        else:
            image_widget.set_paintable(get_default_icon_paintable(size))
    else:
        # Configure Image widget
        if art_source:
            image_widget.set_from_pixbuf(art_source)
        else:
            image_widget.set_from_icon_name("audio-x-generic-symbolic")

        image_widget.set_pixel_size(size)


async def create_overlay_for_album_art(mpd_conn, song, size=100):
    """
    Create an overlay with rounded corners for album art

    Args:
        mpd_conn: The MPD client instance
        song: Dictionary containing song information
        size: Desired size for the album art

    Returns:
        An overlay widget containing the album art with rounded corners
    """
    overlay = Gtk.Overlay()
    picture = Gtk.Picture()

    # Get album art if available
    scaled_pixbuf = None
    if song and mpd_conn.is_connected():
        scaled_pixbuf = await get_album_art_as_pixbuf(
            mpd_conn, song.get("file"), size
        )

    # Set the album art to the picture
    set_widget_album_art(picture, scaled_pixbuf, size, radius=8)
    overlay.set_child(picture)

    return overlay


async def load_album_art(mpd_conn, song, image_widget=None, size=100):
    """
    Load album art for a song and set it to a Gtk.Image or Gtk.Picture widget

    Args:
        mpd_conn: The MPD client instance
        song: Dictionary containing song information
        image_widget: Gtk.Picture or Gtk.Image widget to display the album art
        size: Desired size for the album art
    """
    if not image_widget:
        return

    # Set default icon initially
    set_widget_album_art(image_widget, None, size, radius=8)

    # Don't try to load album art if no MPD connection or no song
    if not mpd_conn.is_connected() or not song:
        # Ensure we use the default icon when song is None
        return

    # Get album art data from MPD and apply it
    try:
        scaled_pixbuf = await get_album_art_as_pixbuf(mpd_conn, song["file"], size)
        if scaled_pixbuf:
            set_widget_album_art(image_widget, scaled_pixbuf, size, radius=8)
    except Exception as e:
        print(f"Failed to load album art: {e}")
        # Default icon already set, no need to do anything here
