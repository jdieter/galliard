#!/usr/bin/env python3
"""Image cache management for Galliard MPD client"""

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Tuple, Optional
import logging

from galliard.widgets.async_ui_helper import AsyncUIHelper  # noqa: E402

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
        """Initialize the image cache

        Args:
            cache_dir: Optional custom cache directory path. If None, uses XDG cache directory.
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Use XDG cache directory
            xdg_cache_home = os.environ.get('XDG_CACHE_HOME')
            if xdg_cache_home:
                self.cache_dir = Path(xdg_cache_home) / 'galliard'
            else:
                self.cache_dir = Path.home() / '.cache' / 'galliard'

        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectory for image data
        self.images_dir = self.cache_dir / 'images'
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectory for forward mapping
        self.mapping_dir = self.cache_dir / 'mapping'
        self.mapping_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectory for reverse mapping
        self.reverse_mapping_dir = self.cache_dir / 'reverse_mapping'
        self.reverse_mapping_dir.mkdir(parents=True, exist_ok=True)

    def _get_image_hash(self, image_data: bytes) -> str:
        """Calculate SHA256 hash of image data

        Args:
            image_data: Binary image data

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(image_data).hexdigest()

    def _get_extension(self, mime_type: str) -> str:
        """Get file extension for a mime type

        Args:
            mime_type: MIME type string

        Returns:
            File extension with leading dot, defaults to .jpg
        """
        return MIME_TO_EXT.get(mime_type, '.jpg')

    def _get_mime_type(self, file_path: Path) -> str:
        """Get mime type from file extension

        Args:
            file_path: Path to file

        Returns:
            MIME type string, defaults to image/jpeg
        """
        # Get the extension (including the dot)
        ext = file_path.suffix.lower()
        return EXT_TO_MIME.get(ext, 'image/jpeg')

    def _get_image_path(self, image_hash: str, mime_type: str) -> Path:
        """Get path to cached image file

        Args:
            image_hash: SHA256 hash of the image data
            mime_type: MIME type of the image

        Returns:
            Path to the image file with appropriate extension
        """
        extension = self._get_extension(mime_type)
        return self.images_dir / (image_hash + extension)

    def _get_mapping_path(self, image_file: str) -> Path:
        """Get path to mapping file for an image file

        Args:
            image_file: Image file name

        Returns:
            Path to the mapping file
        """
        image_file = image_file.replace('/', '_').replace(':', '_')
        return self.mapping_dir / image_file

    def get_image_path(self, song_uri: str) -> Optional[str]:
        """Get path to cached image file for a song URI

        Args:
            song_uri: Song URI string

        Returns:
            Path to the hashed image file if found, None otherwise
        """
        symlink_path = self._get_mapping_path(song_uri)

        # Check if symlink exists and is valid
        if not symlink_path.exists() or not symlink_path.is_symlink():
            return None

        try:
            # Read the image data
            image_path = symlink_path.resolve()
            if not image_path.exists():
                # Broken symlink, clean it up
                symlink_path.unlink()
                return None

            return str(image_path)
        except (OSError, IOError) as e:
            logging.warning(f"Error reading cached image: {e}")
            return None

    def get(self, song_uri: str) -> Optional[Tuple[bytes, str, str]]:
        """Get cached image data for a song URI

        Args:
            song_uri: Song URI string

        Returns:
            Tuple of (binary_data, mime_type, key) if found, None otherwise
        """
        try:
            image_path = self.get_image_path(song_uri)
            if not image_path:
                return None

            # Read from disk
            with open(image_path, 'rb') as f:
                image_data = f.read()

            # Determine mime type from file extension
            mime_type = self._get_mime_type(Path(image_path))

            return image_data, mime_type, str(image_path)
        except (OSError, IOError) as e:
            print(f"Error reading cached image: {e}")
            return None

    def put(self, song_uri: str, image_data: bytes, mime_type: str) -> Optional[str]:
        """Cache image data for a song URI

        Args:
            song_uri: Song URI string
            image_data: Binary image data
            mime_type: MIME type of the image

        Returns:
            key if successful, None otherwise
        """
        try:
            # Calculate hash of image data
            image_hash = self._get_image_hash(image_data)
            image_path = self._get_image_path(image_hash, mime_type)

            # Write image data if not already present
            if not image_path.exists():
                with open(image_path, 'wb') as f:
                    f.write(image_data)

            # Create symlink from URI hash to image file
            symlink_path = self._get_mapping_path(song_uri)

            # Remove existing symlink if present
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()

            # Create new symlink (relative path for portability)
            symlink_path.symlink_to(image_path)

            return str(image_path)
        except (OSError, IOError) as e:
            print(f"Error caching image: {e}")
            return None

    def clear(self) -> None:
        """Clear all cached images"""
        try:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.images_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, IOError) as e:
            print(f"Error clearing cache: {e}")

    def get_cache_size(self) -> int:
        """Get total size of cached images in bytes

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            for file_path in self.images_dir.iterdir():
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except (OSError, IOError) as e:
            print(f"Error calculating cache size: {e}")
        return total_size
