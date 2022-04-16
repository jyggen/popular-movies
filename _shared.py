import copy
import math
import re
from typing import Iterator

import imdb

_COMMON_WORDS = re.compile(r"\b(a|an|the|and|or|of)\b\s?", flags=re.IGNORECASE)
_DUPLICATE_SPACES = re.compile(r"\s{2,}")
_PARENTHESES = re.compile(r"\(.*\)")
_PUNCTUATIONS = re.compile(r"[^\w\s]")
_SPECIAL_CHARS = re.compile(r"([&:\\/])+")
_WORD_DELIMITERS = re.compile(r"(\s|\.|,|_|-|=|'|\|)+")

_IMDB_API = imdb.IMDb()


def _calculate_scores(items: list[dict]) -> list[dict]:
    items = list(copy.deepcopy(items))
    max_value = math.log10(
        max(items, key=lambda item: item["popularity"])["popularity"]
    )
    min_value = math.log10(
        min(items, key=lambda item: item["popularity"])["popularity"]
    )

    for item in items:
        imdb_rating = _IMDB_API.get_movie(item["imdb_id"][2:])["rating"]
        item["score"] = (
            (math.log10(item["popularity"]) - min_value) / (max_value - min_value) * 100
        ) * (imdb_rating / 10)

    return items


def _get_title_variants(title: str) -> Iterator[str]:
    yield title

    normalized = _PARENTHESES.sub("", title).rstrip()

    if normalized != title:
        yield normalized


def _get_year_variants(year: int) -> Iterator[int]:
    yield year
    yield year - 1
    yield year + 1


def _sort_key(title: str) -> str:
    title = _WORD_DELIMITERS.sub(" ", title)
    title = _PUNCTUATIONS.sub("", title)
    title = _COMMON_WORDS.sub("", title)
    title = _DUPLICATE_SPACES.sub(" ", title)
    title = _SPECIAL_CHARS.sub("", title)

    return title.strip().lower()
