import logging
from collections import OrderedDict
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GdkPixbuf, Gdk, Gtk  # noqa: E402

from galliard.models import Song  # noqa: E402
from galliard.utils.async_task_queue import AsyncUIHelper  # noqa: E402

_album_art_cache = OrderedDict()
_MAX_CACHE_SIZE = 2000  # Max number of cached album arts

_rounded_css_installed = False


def _ensure_rounded_css(radius=8):
    """Install the ``.rounded`` border-radius provider on the default display, once."""
    global _rounded_css_installed
    if _rounded_css_installed:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(f".rounded {{ border-radius: {radius}px; }}".encode())
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _rounded_css_installed = True


async def get_album_art_as_pixbuf(mpd_conn, audio_file, size):
    """Return a ``GdkPixbuf.Pixbuf`` of ``audio_file``'s art, scaled to ``size``.

    Hits a process-wide LRU cache keyed by ``(image_path, size)`` before
    fetching from MPD. The aspect ratio is preserved; ``size`` bounds the
    longer edge.
    """
    if not mpd_conn.is_connected() or not audio_file:
        return None

    cache_location = mpd_conn.image_cache.get_image_path(audio_file)
    logging.debug(f"Cache location for {audio_file}: {cache_location}")
    if cache_location:
        cache_key = (cache_location, size)
        if cache_key in _album_art_cache:
            _album_art_cache.move_to_end(cache_key)
            logging.debug(f"Album art cache hit for {audio_file} at size {size}")
            return _album_art_cache[cache_key]

    try:
        binary_data, _, key = await mpd_conn.async_get_album_art(audio_file)
        logging.debug(f"Album art data length: {len(binary_data) if binary_data else 'None'}")
        if binary_data:
            loader = GdkPixbuf.PixbufLoader.new()
            loader.write(binary_data)
            loader.close()

            pixbuf = loader.get_pixbuf()
            if pixbuf:
                # Scale so the longer edge is exactly `size`.
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
                _album_art_cache[cache_key] = scaled_pixbuf
                _album_art_cache.move_to_end(cache_key)

                # LRU eviction when the cache outgrows the cap.
                if len(_album_art_cache) > _MAX_CACHE_SIZE:
                    _album_art_cache.popitem(last=False)

                logging.debug(f"Album art cached for {audio_file} at size {size} ({len(_album_art_cache)} items in cache)")
                return scaled_pixbuf
    except Exception as e:
        logging.info(f"Failed to get album art: {e}")

    return None


def apply_rounded_corners_to_picture(picture, radius=5):
    """Clip ``picture`` to a rounded rectangle via CSS + overflow hidden."""
    picture.set_overflow(Gtk.Overflow.HIDDEN)
    picture.add_css_class("rounded")

    css_provider = Gtk.CssProvider()
    css = f"""
    .rounded {{
        border-radius: {radius}px;
    }}
    """
    css_provider.load_from_data(css.encode())

    if display := Gdk.Display.get_default():
        Gtk.StyleContext.add_provider_for_display(
            display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def get_default_icon_paintable(size):
    """Return a ``Gtk.IconPaintable`` for the fallback ``audio-x-generic-symbolic`` icon."""
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
    """Put ``art_source`` (or the fallback icon) on a Gtk.Picture or Gtk.Image.

    Also sizes the widget: ``set_size_request(size, size)`` for Pictures and
    ``set_pixel_size(size)`` for Images. Callers that manage widget size
    themselves should use :func:`bind_art_to_widget` instead.
    """
    is_picture = isinstance(image_widget, Gtk.Picture)

    if is_picture:
        image_widget.set_size_request(size, size)
        apply_rounded_corners_to_picture(image_widget, radius=radius)

        if art_source:
            image_widget.set_paintable(Gdk.Texture.new_for_pixbuf(art_source))
        else:
            image_widget.set_paintable(get_default_icon_paintable(size))
    else:
        if art_source:
            image_widget.set_from_pixbuf(art_source)
        else:
            image_widget.set_from_icon_name("audio-x-generic-symbolic")

        image_widget.set_pixel_size(size)


async def create_overlay_for_album_art(mpd_conn, song, size=100):
    """Build a rounded-corner Gtk.Overlay containing ``song``'s album art."""
    overlay = Gtk.Overlay()
    picture = Gtk.Picture()

    scaled_pixbuf = None
    if song and mpd_conn.is_connected():
        scaled_pixbuf = await get_album_art_as_pixbuf(
            mpd_conn, song.get("file"), size
        )

    set_widget_album_art(picture, scaled_pixbuf, size, radius=8)
    overlay.set_child(picture)

    return overlay


def _file_from(song_or_path):
    """Coerce a :class:`Song` or raw path string to the MPD file URI."""
    if isinstance(song_or_path, Song):
        return song_or_path.file
    return song_or_path


def fetch_art_async(
    mpd_conn,
    song_or_path,
    size,
    on_result,
    *,
    task_id=None,
    task_priority=110,
):
    """Queue an async album-art fetch for ``song_or_path``.

    ``on_result(pixbuf_or_None)`` fires on the GLib main loop once the
    fetch completes. ``task_id`` / ``task_priority`` are forwarded to
    :class:`AsyncUIHelper` for cancellation and scheduling.
    """
    audio_file = _file_from(song_or_path)
    if audio_file is None:
        on_result(None)
        return

    async def _fetch():
        return await get_album_art_as_pixbuf(mpd_conn, audio_file, size)

    AsyncUIHelper.run_async_operation(
        _fetch,
        on_result,
        task_id=task_id,
        task_priority=task_priority,
    )


def _put_art(widget, pixbuf):
    """Set ``pixbuf`` (or the fallback icon) on ``widget`` without resizing it.

    Unlike :func:`set_widget_album_art`, this preserves the widget's
    caller-chosen geometry so the ``fetch_size`` used to request MPD's art
    can differ from the widget's displayed size.
    """
    if isinstance(widget, Gtk.Picture):
        # A plain Gtk.Picture doesn't clip its paintable; install the
        # .rounded class + overflow once per widget so the texture gets
        # rounded corners to match the placeholder icon paintable.
        if not getattr(widget, "_rounded_configured", False):
            _ensure_rounded_css()
            widget.set_overflow(Gtk.Overflow.HIDDEN)
            widget.add_css_class("rounded")
            widget._rounded_configured = True
        if pixbuf is not None:
            widget.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            widget.set_paintable(None)
    else:
        if pixbuf is not None:
            widget.set_from_pixbuf(pixbuf)
        else:
            widget.set_from_icon_name("audio-x-generic-symbolic")


def bind_art_to_widget(
    mpd_conn,
    widget,
    song_or_path,
    fetch_size,
    *,
    task_id=None,
    task_priority=110,
):
    """Async-load the album art for ``song_or_path`` onto ``widget``.

    ``fetch_size`` is the pixel resolution requested from MPD (also the
    cache key). The widget's display size stays whatever the caller
    configured with ``set_pixel_size`` / ``set_size_request`` -- this
    helper doesn't touch geometry.

    Dedupes per-widget: if ``widget`` already shows art for this file,
    the call is a no-op. A ``None`` song renders the default icon.
    """
    audio_file = _file_from(song_or_path)

    if audio_file is not None and getattr(widget, "_loaded_art_file", None) == audio_file:
        return
    widget._loaded_art_file = audio_file

    async def _load_and_set():
        if audio_file is None or not mpd_conn.is_connected():
            _put_art(widget, None)
            widget.pixbuf_data = None
            return
        pixbuf = await get_album_art_as_pixbuf(mpd_conn, audio_file, fetch_size)
        # Another bind may have taken over this widget in the meantime;
        # don't stomp on it with our stale result.
        if getattr(widget, "_loaded_art_file", None) != audio_file:
            return
        _put_art(widget, pixbuf)
        widget.pixbuf_data = pixbuf

    AsyncUIHelper.run_async_operation(
        _load_and_set,
        None,
        task_id=task_id,
        task_priority=task_priority,
    )
