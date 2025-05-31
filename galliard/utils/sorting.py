"""Utility functions for sorting items in the library"""

import unicodedata


def get_sort_key(text, ignore_prefixes=True):
    """
    Generate a sort key for text that ignores common prefixes, is case-insensitive,
    and converts European non-English letters to their ASCII equivalents.

    Args:
        text (str): The text to generate a sort key for
        ignore_prefixes (bool): Whether to ignore common prefixes like "The", "A", "An"

    Returns:
        A normalized string for sorting
    """
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Normalize unicode characters to ASCII equivalents
    # This converts letters like é->e, ñ->n, ö->o, etc.
    # Ensure it works for Ø too
    text = unicodedata.normalize("NFKC", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("ø", "o")

    if ignore_prefixes:
        prefixes = ["the ", "a ", "an "]
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix) :]

    return text
