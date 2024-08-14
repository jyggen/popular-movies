import copy
import math
import re
from typing import Iterator
from tenacity import Retrying, stop_after_attempt, wait_fixed, wait_random

import imdb

_COMMON_WORDS = re.compile(r"\b(a|an|the|and|or|of)\b\s?", flags=re.IGNORECASE)
_DUPLICATE_SPACES = re.compile(r"\s{2,}")
_PARENTHESES = re.compile(r"\(.*\)")
_PUNCTUATIONS = re.compile(r"[^\w\s]")
_SPECIAL_CHARS = re.compile(r"([&:\\/])+")
_WORD_DELIMITERS = re.compile(r"(\s|\.|,|_|-|=|'|\|)+")

_IMDB_API = imdb.Cinemagoer()


def _calculate_scores(items: list[dict]) -> list[dict]:
    items = list(copy.deepcopy(items))

    if not items:
        return []

    max_value = max(items, key=lambda item: item["popularity"])["popularity"]

    if max_value > 0:
        max_value = math.log10(max_value)

    min_value = min(items, key=lambda item: item["popularity"])["popularity"]

    if min_value > 0:
        min_value = math.log10(min_value)

    for item in items:
        if item["imdb_id"] == "" or item["imdb_id"] is None:
            imdb_rating = 0
        else:
            for attempt in Retrying(
                    wait=wait_fixed(3) + wait_random(0, 2), stop=stop_after_attempt(3)
                ):
                    with attempt:
                        try:
                            imdb_rating = _IMDB_API.get_movie(item["imdb_id"][2:])["rating"]
                        except KeyError:
                            imdb_rating = 0

        if max_value == min_value:
            item["score"] = imdb_rating / 10
        else:
            popularity = item["popularity"]

            if popularity > 0:
                popularity = math.log10(popularity)

            item["score"] = (
                (popularity - min_value) / (max_value - min_value) * 100
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
