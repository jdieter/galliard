"""Utility functions for sorting items in the library"""

import unicodedata


def get_sort_key(text, ignore_prefixes=True):
    """Return a normalised sort key for ``text``.

    Lower-cased and unicode-folded (so ``é``/``ö``/``ø`` sort next to their
    ASCII counterparts). When ``ignore_prefixes`` is set, leading ``the``,
    ``a``, ``an`` are stripped so "The Beatles" sorts under B.
    """
    if not text:
        return ""

    text = text.lower()

    # Decompose accented characters and drop the combining marks so
    # diacritics don't split letters across sort buckets.
    text = unicodedata.normalize("NFKC", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("ø", "o")

    if ignore_prefixes:
        prefixes = ["the ", "a ", "an "]
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix) :]

    return text
