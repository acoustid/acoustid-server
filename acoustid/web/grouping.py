"""Grouping of user-submitted metadata on the track page.

The same title is submitted in many spellings. Rows whose title and artist
are equal after ignoring case, accents and punctuation are grouped, and
each group shows its most common spelling.
"""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class MetaRow:
    title: str
    artist: str
    album: str
    sources: int


@dataclass
class Album:
    name: str
    sources: int


@dataclass
class MetaGroup:
    title: str
    artist: str
    sources: int
    spellings: int
    albums: list[Album] = field(default_factory=list)
    rows: list[MetaRow] = field(default_factory=list)


def normalize(text: str) -> str:
    """Lowercases, drops accents and turns runs of punctuation and spaces into one space."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    words = []
    word = []
    for ch in decomposed:
        category = unicodedata.category(ch)
        if category == "Mn":
            continue
        if category[0] in "LN":
            word.append(ch.lower())
        elif word:
            words.append("".join(word))
            word = []
    if word:
        words.append("".join(word))
    return " ".join(words)


def _most_common(counts: dict[str, int]) -> str:
    best, best_count = "", -1
    for name, count in counts.items():
        if count > best_count:
            best, best_count = name, count
    return best


def group_metadata(rows: list[MetaRow]) -> list[MetaGroup]:
    """Groups rows by normalized title and artist, most submitted first."""
    by_key: dict[tuple[str, str], list[MetaRow]] = {}
    for row in rows:
        key = (normalize(row.title), normalize(row.artist))
        by_key.setdefault(key, []).append(row)

    groups = []
    for members in by_key.values():
        members = sorted(members, key=lambda r: r.sources, reverse=True)
        titles: dict[str, int] = defaultdict(int)
        artists: dict[str, int] = defaultdict(int)
        albums: dict[str, dict[str, int]] = {}
        for r in members:
            titles[r.title] += r.sources
            artists[r.artist] += r.sources
            if r.album:
                spellings = albums.setdefault(normalize(r.album), defaultdict(int))
                spellings[r.album] += r.sources
        groups.append(
            MetaGroup(
                title=_most_common(titles),
                artist=_most_common(artists),
                sources=sum(r.sources for r in members),
                spellings=len({(r.title, r.artist) for r in members}),
                albums=sorted(
                    (Album(_most_common(s), sum(s.values())) for s in albums.values()),
                    key=lambda a: a.sources,
                    reverse=True,
                ),
                rows=members,
            )
        )
    groups.sort(key=lambda g: g.sources, reverse=True)
    return groups
