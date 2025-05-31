#!/usr/bin/env python3

import json
from pathlib import Path
from xdg.BaseDirectory import xdg_config_home
import logging


class Config:
    """Configuration manager for Galliard"""

    def __init__(self):
        """Initialize the configuration manager"""
        self.config_dir = Path(xdg_config_home) / "galliard"
        self.config_file = self.config_dir / "config.json"
        self.config = self.get_default_config()

    def get_default_config(self):
        """Get default configuration"""
        return {
            "mpd": {
                "host": "localhost",
                "port": 6600,
                "password": None,
                "timeout": 10,
            },
            "ui": {
                "theme": "system",
                "show_album_art": True,
                "show_notifications": True,
                "minimize_to_tray": True,
            },
            "auto_connect": True,
        }

    def load(self):
        """Load configuration from file"""
        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load config file if it exists
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                logging.error(f"Error loading config file: {e}")
        else:
            # Create default config file
            self.save()

    def save(self):
        """Save configuration to file"""
        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Save config to file
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config file: {e}")

    def get(self, key, default=None):
        """Get a configuration value"""
        # Handle nested keys with dot notation
        if "." in key:
            parts = key.split(".")
            value = self.config
            for part in parts:
                if part in value:
                    value = value[part]
                else:
                    return default
            return value

        # Handle simple keys
        return self.config.get(key, default)

    def set(self, key, value):
        """Set a configuration value"""
        # Handle nested keys with dot notation
        if "." in key:
            parts = key.split(".")
            config = self.config
            for part in parts[:-1]:
                if part not in config:
                    config[part] = {}
                config = config[part]
            config[parts[-1]] = value
        else:
            # Handle simple keys
            self.config[key] = value

        # Save changes
        self.save()
