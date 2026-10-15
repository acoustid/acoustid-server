"""Jinja filters for formatting numbers on the website."""

from flask import Flask


def thousands(value: int | float | None) -> str:
    """76476275 -> "76,476,275" """
    if value is None:
        return "–"
    return "{:,}".format(int(value))


def compact(value: int | float | None) -> str:
    """94437270 -> "94.4M" """
    if value is None:
        return "–"
    for unit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= unit:
            text = "{:.1f}".format(value / unit)
            if text.endswith(".0"):
                text = text[:-2]
            return text + suffix
    return "{:.0f}".format(value)


def duration(seconds: int | float | None) -> str:
    """637 -> "10:37" """
    if seconds is None:
        return "–"
    seconds = int(round(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def percent(fraction: float | None, digits: int = 1) -> str:
    """0.305 -> "30.5 %" """
    if fraction is None:
        return "–"
    return "{:.{}f} %".format(100 * fraction, digits)


def bar_width(value: int | float | None, maximum: int | float | None) -> str:
    """A bar length as a percentage of the largest value, for a width style."""
    if not value or not maximum:
        return "0"
    return "{:.1f}".format(100 * value / maximum)


def score_style(score: float) -> str:
    """Background and text color for a similarity score.

    Matches blend from the sunken background to the link blue, so
    differences between good matches stay visible; weaker scores get a tint
    of the verdict color.
    """
    bg = (0xEC, 0xEB, 0xE6)
    if score < 0.6:
        tint = (0xAA, 0x00, 0x00) if score < 0.35 else (0x8A, 0x5A, 0x00)
        rgb = [round(b + (t - b) * 0.35) for b, t in zip(bg, tint)]
        return "background:rgb(%d,%d,%d);color:#1a1a1a" % tuple(rgb)
    blue = (0x01, 0x45, 0xAA)
    t = 0.15 + 0.85 * min(1.0, (score - 0.6) / 0.4)
    rgb = [round(b + (c - b) * t) for b, c in zip(bg, blue)]
    color = "#fff" if t > 0.55 else "#1a1a1a"
    return "background:rgb(%d,%d,%d);color:%s" % (rgb[0], rgb[1], rgb[2], color)


def verdict(score: float) -> tuple[str, str]:
    """CSS class and label for a similarity score."""
    if score >= 0.6:
        return "good", "Same recording"
    if score >= 0.35:
        return "warn", "Possibly related"
    return "bad", "Different audio"


def register_filters(app: Flask) -> None:
    app.jinja_env.filters["thousands"] = thousands
    app.jinja_env.filters["compact"] = compact
    app.jinja_env.filters["duration"] = duration
    app.jinja_env.filters["percent"] = percent
    app.jinja_env.filters["bar_width"] = bar_width
    app.jinja_env.filters["score_style"] = score_style
    app.jinja_env.filters["verdict"] = verdict
