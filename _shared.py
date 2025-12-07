import copy
import math
import re
import requests
import time
from typing import Iterator
from tenacity import Retrying, stop_after_attempt, wait_fixed, wait_random

_COMMON_WORDS = re.compile(r"\b(a|an|the|and|or|of)\b\s?", flags=re.IGNORECASE)
_DUPLICATE_SPACES = re.compile(r"\s{2,}")
_PARENTHESES = re.compile(r"\(.*\)")
_PUNCTUATIONS = re.compile(r"[^\w\s]")
_SPECIAL_CHARS = re.compile(r"([&:\\/])+")
_WORD_DELIMITERS = re.compile(r"(\s|\.|,|_|-|=|'|\|)+")

_session = requests.Session()


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
            imdb_rating = 50
            metacritic_rating = 50
        else:
            for attempt in Retrying(
                wait=wait_fixed(3) + wait_random(0, 2), stop=stop_after_attempt(3)
            ):
                with attempt:
                    response = _session.get(
                        f"https://api.imdbapi.dev/titles/{item["imdb_id"]}"
                    )

                    if response.status_code == 404:
                        imdb_rating = 0
                        break

                    response.raise_for_status()
                    data = response.json()

                    try:
                        imdb_rating = data["rating"]["aggregateRating"] * 10
                    except KeyError:
                        imdb_rating = 50

                    try:
                        metacritic_rating = data["metacritic"]["score"]
                    except KeyError:
                        metacritic_rating = 50

        if max_value == min_value:
            item["score"] = (imdb_rating + metacritic_rating) / 2
        else:
            popularity = item["popularity"]

            if popularity > 0:
                popularity = math.log10(popularity)

            item["score"] = (
                ((popularity - min_value) / (max_value - min_value) * 100)
                + imdb_rating
                + metacritic_rating
            ) / 3

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


def _get_poster_url(imdb_id: str) -> str:
    while True:
        response = _session.get(
            f"https://posters.metadb.info/imdb/{imdb_id}", allow_redirects=False
        )

        if response.status_code == 202 or response.status_code == 503:
            time.sleep(int(response.headers.get("Retry-After")))
        elif response.status_code == 303:
            return response.headers.get("Location")
        else:
            response.raise_for_status()
