"""group_artist_names: split on ' / ' and merge case-variant duplicates."""

from galliard.utils.artists import group_artist_names


def _by_display(groups):
    """Sort pairs by display name for order-independent assertions."""
    return sorted(groups, key=lambda pair: pair[0])


class TestSplit:
    def test_slash_joined_name_becomes_two_rows(self):
        result = group_artist_names(["Quantum Ferrets / The Waffle Cartel"])
        assert _by_display(result) == [
            ("Quantum Ferrets", ["Quantum Ferrets / The Waffle Cartel"]),
            ("The Waffle Cartel", ["Quantum Ferrets / The Waffle Cartel"]),
        ]

    def test_triple_slash_joined_name(self):
        result = group_artist_names(["Sockpuppet Supreme / Velcro Orchestra / Llama Bazaar"])
        displays = sorted(display for display, _ in result)
        assert displays == ["Llama Bazaar", "Sockpuppet Supreme", "Velcro Orchestra"]
        for _, aliases in result:
            assert aliases == ["Sockpuppet Supreme / Velcro Orchestra / Llama Bazaar"]

    def test_slash_without_surrounding_spaces_is_not_split(self):
        # No spaces around the slash, so "DJ Ham/Cheese" is a single name.
        result = group_artist_names(["DJ Ham/Cheese"])
        assert result == [("DJ Ham/Cheese", ["DJ Ham/Cheese"])]

    def test_empty_and_whitespace_parts_are_skipped(self):
        result = group_artist_names(["Dancing Potatoes /  / The Goose Conspiracy"])
        displays = sorted(display for display, _ in result)
        assert displays == ["Dancing Potatoes", "The Goose Conspiracy"]


class TestCaseMerge:
    def test_exact_duplicates_collapse_to_one_row(self):
        result = group_artist_names(["Wombat Philharmonic", "Wombat Philharmonic"])
        assert result == [("Wombat Philharmonic", ["Wombat Philharmonic"])]

    def test_case_variants_collapse_to_one_row(self):
        result = group_artist_names(["Wombat Philharmonic", "wombat philharmonic"])
        assert len(result) == 1
        display, aliases = result[0]
        assert display == "Wombat Philharmonic"
        assert sorted(aliases) == ["Wombat Philharmonic", "wombat philharmonic"]

    def test_most_common_capitalisation_wins(self):
        # "wombat philharmonic" x2 beats "Wombat Philharmonic" x1.
        result = group_artist_names([
            "Wombat Philharmonic",
            "wombat philharmonic",
            "wombat philharmonic",
        ])
        assert result[0][0] == "wombat philharmonic"

    def test_tie_falls_to_first_seen(self):
        result = group_artist_names(["wombat philharmonic", "Wombat Philharmonic"])
        assert result[0][0] == "wombat philharmonic"


class TestSplitAndMergeInteract:
    def test_split_part_unifies_with_existing_artist(self):
        # "Dancing Potatoes" appears both alone and as part of a compound
        # tag -- one display row with both raw strings as aliases.
        result = group_artist_names([
            "Dancing Potatoes / The Goose Conspiracy",
            "Dancing Potatoes",
        ])
        by_display = {display: aliases for display, aliases in result}
        assert set(by_display) == {"Dancing Potatoes", "The Goose Conspiracy"}
        assert sorted(by_display["Dancing Potatoes"]) == [
            "Dancing Potatoes",
            "Dancing Potatoes / The Goose Conspiracy",
        ]
        assert by_display["The Goose Conspiracy"] == [
            "Dancing Potatoes / The Goose Conspiracy"
        ]


class TestEdgeCases:
    def test_empty_input(self):
        assert group_artist_names([]) == []

    def test_none_and_empty_strings_are_ignored(self):
        assert group_artist_names([None, "", "   "]) == []

    def test_generator_input(self):
        result = group_artist_names(
            name for name in ["Quantum Ferrets", "quantum ferrets"]
        )
        assert len(result) == 1
        assert result[0][0] == "Quantum Ferrets"
