#!/usr/bin/env python3
"""Image cache management for Galliard MPD client"""

import hashlib
import os
from pathlib import Path
from typing import Tuple, Optional
import logging

# Mapping from mime types to file extensions
MIME_TO_EXT = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/tiff': '.tiff',
    'image/svg+xml': '.svg',
}

# Mapping from file extensions to mime types
EXT_TO_MIME = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.tiff': 'image/tiff',
    '.tif': 'image/tiff',
    '.svg': 'image/svg+xml',
}


class ImageCache:
    """Cache for album art images stored in XDG cache directory"""

    def __init__(self, cache_dir: Optional[str] = None):
        """Open (and create, if needed) the image cache directory tree.

        Uses ``$XDG_CACHE_HOME/galliard`` (or ``~/.cache/galliard``) unless
        ``cache_dir`` overrides it.
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            xdg_cache_home = os.environ.get('XDG_CACHE_HOME')
            if xdg_cache_home:
                self.cache_dir = Path(xdg_cache_home) / 'galliard'
            else:
                self.cache_dir = Path.home() / '.cache' / 'galliard'

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Images are stored by content hash; the mapping/ directory holds
        # per-URI symlinks into images/ so the same file is only stored
        # once even when multiple songs share album art.
        self.images_dir = self.cache_dir / 'images'
        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.mapping_dir = self.cache_dir / 'mapping'
        self.mapping_dir.mkdir(parents=True, exist_ok=True)

        self.reverse_mapping_dir = self.cache_dir / 'reverse_mapping'
        self.reverse_mapping_dir.mkdir(parents=True, exist_ok=True)

    def _get_image_hash(self, image_data: bytes) -> str:
        """Return the hex SHA256 of ``image_data``."""
        return hashlib.sha256(image_data).hexdigest()

    def _get_extension(self, mime_type: str) -> str:
        """Return the file extension (with leading dot) for ``mime_type``."""
        return MIME_TO_EXT.get(mime_type, '.jpg')

    def _get_mime_type(self, file_path: Path) -> str:
        """Return the MIME type implied by ``file_path``'s extension."""
        ext = file_path.suffix.lower()
        return EXT_TO_MIME.get(ext, 'image/jpeg')

    def _get_image_path(self, image_hash: str, mime_type: str) -> Path:
        """Return the on-disk path for a cached image with the given hash."""
        extension = self._get_extension(mime_type)
        return self.images_dir / (image_hash + extension)

    def _get_mapping_path(self, image_file: str) -> Path:
        """Return the mapping-symlink path for a song URI."""
        image_file = image_file.replace('/', '_').replace(':', '_')
        return self.mapping_dir / image_file

    def get_image_path(self, song_uri: str) -> Optional[str]:
        """Return the cached image path for ``song_uri``, or None if missing.

        Broken symlinks are cleaned up on discovery so the next ``put`` can
        re-create them cleanly.
        """
        symlink_path = self._get_mapping_path(song_uri)

        if not symlink_path.exists() or not symlink_path.is_symlink():
            return None

        try:
            image_path = symlink_path.resolve()
            if not image_path.exists():
                symlink_path.unlink()
                return None
            return str(image_path)
        except (OSError, IOError) as e:
            logging.warning(f"Error reading cached image: {e}")
            return None

    def get(self, song_uri: str) -> Optional[Tuple[bytes, str, str]]:
        """Return ``(data, mime_type, path)`` for ``song_uri``, or None."""
        try:
            image_path = self.get_image_path(song_uri)
            if not image_path:
                return None

            with open(image_path, 'rb') as f:
                image_data = f.read()

            mime_type = self._get_mime_type(Path(image_path))

            return image_data, mime_type, str(image_path)
        except (OSError, IOError) as e:
            print(f"Error reading cached image: {e}")
            return None

    def put(self, song_uri: str, image_data: bytes, mime_type: str) -> Optional[str]:
        """Write ``image_data`` into the cache and symlink it from ``song_uri``.

        Returns the on-disk path of the stored file, or None on I/O error.
        """
        try:
            image_hash = self._get_image_hash(image_data)
            image_path = self._get_image_path(image_hash, mime_type)

            # Content-addressed: only write if another song didn't already
            # store the same bytes.
            if not image_path.exists():
                with open(image_path, 'wb') as f:
                    f.write(image_data)

            symlink_path = self._get_mapping_path(song_uri)
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            symlink_path.symlink_to(image_path)

            return str(image_path)
        except (OSError, IOError) as e:
            print(f"Error caching image: {e}")
            return None

    def clear(self) -> None:
        """Delete every cached image and recreate the empty directory tree."""
        try:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.images_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, IOError) as e:
            print(f"Error clearing cache: {e}")

    def get_cache_size(self) -> int:
        """Return the total size of cached images in bytes."""
        total_size = 0
        try:
            for file_path in self.images_dir.iterdir():
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except (OSError, IOError) as e:
            print(f"Error calculating cache size: {e}")
        return total_size
