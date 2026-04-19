# Galliard Test Suite

Pyramid of tests, each tier skipping gracefully when its prerequisites
aren't installed. Shape:

| Tier          | Lives in              | Requires                          |
|---------------|-----------------------|-----------------------------------|
| Unit          | `tests/unit/`         | `pytest`, `pytest-asyncio`        |
| Mocked MPD    | `tests/integration/`  | the above                         |
| Live MPD      | `tests/live/`         | `mpd` binary on `$PATH`           |
| Gtk smoke     | `tests/smoke/`        | Gtk4 + libadwaita + display       |

The `data/` subdirectory holds sample mp3s used by the live tier.

## Quick start

```
pip install -e .[test]
pytest
```

Unit and mocked tiers always run. Live MPD and Gtk smoke tests show as
`SKIPPED` when their prerequisites aren't present.

## Selectors

```
pytest tests/unit             # fast, no system deps
pytest -m 'not live_mpd'      # skip the live tier even if mpd is installed
pytest -m live_mpd            # run only the live tier
```

## Containerised runs

For a deterministic full-pyramid run that doesn't depend on what's
installed locally:

```
./tests/run-in-container.sh
```

This uses Podman (falling back to Docker) to build a minimal Fedora
image with mpd, Gtk4, libadwaita, Xvfb, and the Python test deps, then
runs `pytest` inside it against a volume mount of the repo.
