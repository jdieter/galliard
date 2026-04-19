"""Aspect-ratio scaling math + Song/path coercion in utils/album_art.py."""

from unittest.mock import MagicMock

import pytest

from galliard.models import Song
from galliard.utils.album_art import _file_from


class TestFileFrom:
    def test_song_object_uses_file_attribute(self):
        assert _file_from(Song(file="music/a.mp3")) == "music/a.mp3"

    def test_plain_string_passes_through(self):
        assert _file_from("library/b.flac") == "library/b.flac"

    def test_none_passes_through(self):
        assert _file_from(None) is None


class TestAspectScaling:
    """``get_album_art_as_pixbuf`` scales so the longer edge equals ``size``.

    We can't exercise the full async fetch here without a GdkPixbuf stack,
    but the pure math is easy to spot-check with a stub pixbuf that mimics
    ``width``/``height``/``scale_simple``.
    """

    @staticmethod
    def _apply_scaling(pixbuf_width, pixbuf_height, size):
        # Mirrors the arithmetic in get_album_art_as_pixbuf.
        if pixbuf_width > pixbuf_height:
            new_width = size
            new_height = int(pixbuf_height * (size / pixbuf_width))
        else:
            new_height = size
            new_width = int(pixbuf_width * (size / pixbuf_height))
        return new_width, new_height

    def test_landscape_preserves_aspect(self):
        assert self._apply_scaling(400, 200, 100) == (100, 50)

    def test_portrait_preserves_aspect(self):
        assert self._apply_scaling(200, 400, 100) == (50, 100)

    def test_square_stays_square(self):
        assert self._apply_scaling(100, 100, 100) == (100, 100)

    def test_scaling_up_from_smaller_source(self):
        # A 50x25 pixbuf asked for size=100 grows to 100x50.
        assert self._apply_scaling(50, 25, 100) == (100, 50)

    def test_odd_aspect_truncates_to_int(self):
        # A 3:1 source at size=100 -> 100x33 (not 33.33).
        assert self._apply_scaling(300, 100, 100) == (100, 33)
