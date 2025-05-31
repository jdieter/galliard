# Galliard

A modern Music Player Daemon (MPD) client for GNOME, designed to mimic the original GMPC

## Features

- Connect to local and remote MPD servers
- Browse and manage your music library
- Control playbook (play, pause, skip, stop)
- Adjust volume and manage playlists
- Media key support
- GNOME desktop notifications
- Minimalist GTK4 user interface
- System tray integration
- Optional snapcast client volume control

## Requirements

- Python 3.6+
- GTK 4
- python-mpd2
- PyGObject
- MPD server (local or remote)
- python-snapcast (optional)

## Installation

### Install Dependencies

```bash
# Install system dependencies (Fedora)
sudo dnf install python3-gobject gtk4-devel libnotify-devel

# Install Python dependencies from pyproject.toml
pip install .
```

### Running the Application

```bash
python3 -m galliard
```

## Configuration

On first run, the application will create a configuration file at `~/.config/galliard/config.json`.
You can edit this file to change the MPD server connection details.

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
