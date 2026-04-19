from galliard.utils.sorting import get_sort_key


def test_empty_string_returns_empty():
    assert get_sort_key("") == ""


def test_lowercases():
    assert get_sort_key("Beatles") == "beatles"


def test_strips_leading_the():
    assert get_sort_key("The Beatles") == "beatles"


def test_strips_leading_a():
    assert get_sort_key("A Perfect Circle") == "perfect circle"


def test_strips_leading_an():
    assert get_sort_key("An Evening With") == "evening with"


def test_does_not_strip_prefixes_in_middle():
    assert "the " in get_sort_key("Songs for the Deaf")


def test_ignore_prefixes_false_keeps_the():
    assert get_sort_key("The Beatles", ignore_prefixes=False) == "the beatles"


def test_accents_stripped():
    # Without accent-folding, "É" would sort after "Z".
    assert get_sort_key("Éric") == "eric"


def test_nordic_oe():
    # Sigur Rós -> should fold ó to o.
    assert "ros" in get_sort_key("Sigur Rós")


def test_oe_slashed_o():
    # The explicit ø -> o replacement.
    assert get_sort_key("Mø") == "mo"


def test_sort_ordering():
    names = ["The Beatles", "Abba", "Zebra", "Éric"]
    names.sort(key=get_sort_key)
    # "Abba" first, "Beatles" (from The Beatles) next, then "Éric", then "Zebra".
    assert names == ["Abba", "The Beatles", "Éric", "Zebra"]
