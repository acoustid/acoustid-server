from acoustid.web.filters import compact, duration, score_style, thousands, verdict
from acoustid.web.grouping import MetaRow, group_metadata, normalize


def test_normalize() -> None:
    assert normalize("Café del Mar, Vol.20 — CD1") == "cafe del mar vol 20 cd1"
    assert normalize("  Lower Your   Eyelids! ") == "lower your eyelids"
    assert normalize("音轨12") == "音轨12"
    assert normalize("") == ""


def test_group_metadata() -> None:
    rows = [
        MetaRow(
            "Lower Your Eyelids to Die With the Sun",
            "M83",
            "Before the Dawn Heals Us",
            37,
        ),
        MetaRow(
            "Lower Your Eyelids To Die With The Sun",
            "M83",
            "Before The Dawn Heals Us",
            57,
        ),
        MetaRow("Lower Your Eyelids To Die With The Sun", "M83", "Café del Mar 20", 14),
        MetaRow("", "", "", 58),
    ]
    groups = group_metadata(rows)
    assert len(groups) == 2
    first, second = groups
    assert first.sources == 108
    assert first.title == "Lower Your Eyelids To Die With The Sun"
    assert first.spellings == 2
    assert [a.name for a in first.albums] == [
        "Before The Dawn Heals Us",
        "Café del Mar 20",
    ]
    assert [r.sources for r in first.rows] == [57, 37, 14]
    assert second.sources == 58
    assert second.title == ""


def test_filters() -> None:
    assert thousands(76476275) == "76,476,275"
    assert thousands(None) == "–"
    assert compact(94437270) == "94.4M"
    assert compact(30000) == "30K"
    assert compact(911) == "911"
    assert duration(637) == "10:37"
    assert duration(None) == "–"
    assert verdict(0.9) == ("good", "Same recording")
    assert verdict(0.1) == ("bad", "Different audio")
    assert score_style(0.95).endswith("color:#fff")
