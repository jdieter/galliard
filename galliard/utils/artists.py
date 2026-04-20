"""Utilities for normalising MPD artist-tag names for the library view."""


def group_artist_names(raw_names):
    """Split ' / '-joined names and merge case-insensitive duplicates.

    Returns a list of ``(display_name, aliases)`` pairs. ``display_name``
    is whichever capitalisation is most common in the raw data (ties
    broken by first-seen order); ``aliases`` is the list of raw MPD
    artist strings that should be queried to retrieve every album/song
    belonging to this display row.
    """
    groups = {}  # casefold key -> {"counts", "order", "aliases"}
    for raw in raw_names:
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(" / ") if p.strip()]
        for part in parts:
            key = part.casefold()
            entry = groups.setdefault(
                key, {"counts": {}, "order": [], "aliases": []}
            )
            if part not in entry["counts"]:
                entry["counts"][part] = 0
                entry["order"].append(part)
            entry["counts"][part] += 1
            if raw not in entry["aliases"]:
                entry["aliases"].append(raw)

    result = []
    for entry in groups.values():
        # max() returns the first element at the maximum, so ties fall
        # to whichever form was seen first.
        display = max(entry["order"], key=lambda form: entry["counts"][form])
        result.append((display, entry["aliases"]))
    return result
