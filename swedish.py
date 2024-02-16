import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional, Iterator

import requests
import sentry_sdk
from bs4 import BeautifulSoup
from tmdbv3api import Find, Movie, Search

from _shared import (
    _sort_key,
    _calculate_scores,
)

_MAX_RESULTS = 3
_find_api = Find()
_movie_api = Movie()
_search_api = Search()


def _filter_by_release_date(movie: Any) -> bool:
    try:
        release_date = date.fromisoformat(movie["release_date"])
    except KeyError:
        return False

    diff = date.today() - release_date

    return diff <= timedelta(days=90)


def _find_movie_by_imdb_id(imdb_id: str) -> dict | None:
    results = _find_api.find_by_imdb_id(imdb_id)

    if not results["movie_results"]:
        logging.error('Unable to find a match for "{imdb_id}".'.format(imdb_id=imdb_id))
        return None

    match = dict(results["movie_results"][0])
    match["imdb_id"] = imdb_id

    if match["original_language"] != "sv":
        logging.info(
            'Skipping match of "{imdb_id}" against "{title}".'.format(
                imdb_id=imdb_id,
                title=match["title"],
            )
        )
        return None

    logging.info(
        'Matched "{imdb_id}" against "{title}".'.format(
            imdb_id=imdb_id,
            title=match["title"],
        )
    )

    return match


def _get_moviezine_movies() -> Iterator[str]:
    response = requests.get("https://www.moviezine.se/biotoppen")
    body = BeautifulSoup(response.content, features="html.parser")

    if "Biotoppen Sverige" not in body.select_one(".top_toplists_title").text:
        raise ValueError("Unable to parse MovieZine response.")

    for movie in body.select(".top_list_watchable_info .imdb_grade"):
        imdb_id = movie.attrs.get("data-imdb-id")

        if not imdb_id:
            continue

        yield "tt" + imdb_id


def _to_steven_lu_format(movies: list[dict]) -> Iterator[dict]:
    yield from (
        {
            "title": movie["title"],
            "imdb_id": movie["imdb_id"],
            "poster_url": "https://image.tmdb.org/t/p/w500{path}".format(
                path=movie["poster_path"],
            ),
        }
        for movie in movies
    )


def _generate() -> list[dict]:
    movies = filter(
        None,
        [_find_movie_by_imdb_id(imdb_id) for imdb_id in _get_moviezine_movies()],
    )

    movies = filter(_filter_by_release_date, movies)
    movies = _calculate_scores(list(movies))
    movies = sorted(movies, key=lambda movie: movie["score"], reverse=True)
    movies = _to_steven_lu_format(movies[:_MAX_RESULTS])

    return sorted(movies, key=lambda movie: _sort_key(movie["title"]))


if __name__ == "__main__":
    sentry_sdk.init(os.environ.get("SENTRY_DSN"), traces_sample_rate=1)

    with sentry_sdk.start_transaction(op="generate", name="Generate Movies"):
        print(json.dumps(_generate(), indent=4))  # noqa: WPS421
