#!/usr/bin/env python3

import json
from pathlib import Path
from xdg.BaseDirectory import xdg_config_home
import logging


class Config:
    """Configuration manager for Galliard"""

    def __init__(self):
        """Prepare config paths and seed in-memory settings with defaults."""
        self.config_dir = Path(xdg_config_home) / "galliard"
        self.config_file = self.config_dir / "config.json"
        self.config = self.get_default_config()

    def get_default_config(self):
        """Return the built-in defaults merged into on first run."""
        return {
            "mpd": {
                "host": "localhost",
                "port": 6600,
                "password": None,
                "timeout": 10,
            },
            "ui": {
                "theme": "system",
                "show_notifications": True,
                "minimize_to_tray": True,
            },
            "auto_connect": True,
        }

    def load(self):
        """Load configuration from disk, creating the file on first run."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                logging.error(f"Error loading config file: {e}")
        else:
            self.save()

    def save(self):
        """Write the current in-memory config back to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config file: {e}")

    def get(self, key, default=None):
        """Look up ``key`` (supports ``a.b.c`` dotted paths)."""
        if "." in key:
            parts = key.split(".")
            value = self.config
            for part in parts:
                if part in value:
                    value = value[part]
                else:
                    return default
            return value

        return self.config.get(key, default)

    def set(self, key, value):
        """Set ``key`` (supports dotted paths, creating intermediate dicts)."""
        if "." in key:
            parts = key.split(".")
            config = self.config
            for part in parts[:-1]:
                if part not in config:
                    config[part] = {}
                config = config[part]
            config[parts[-1]] = value
        else:
            self.config[key] = value

        self.save()
