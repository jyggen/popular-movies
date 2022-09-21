import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional, Iterator

import requests
import sentry_sdk
from bs4 import BeautifulSoup
from tmdbv3api import Movie, Search

from _shared import (
    _sort_key,
    _calculate_scores,
    _get_year_variants,
    _get_title_variants,
)

_MAX_RESULTS = 12
_movie_api = Movie()
_search_api = Search()


def _best_match(a: dict, b: Optional[dict], title: str, year: int) -> dict:
    if b is None:
        return a

    if a["title"] == title and b["title"] != title:
        return a

    if a["title"] != title and b["title"] == title:
        return b

    a_has_release_date = "release_date" in a and a["release_date"]
    b_has_release_date = "release_date" in b and b["release_date"]

    if a_has_release_date and not b_has_release_date:
        return a

    if not a_has_release_date and b_has_release_date:
        return b

    if a_has_release_date and b_has_release_date:
        a_date = date.fromisoformat(a["release_date"])
        b_date = date.fromisoformat(b["release_date"])

        if abs(a_date.year - year) > abs(b_date.year - year):
            return b

        if abs(a_date.year - year) < abs(b_date.year - year):
            return a

    if a["popularity"] > b["popularity"]:
        return a

    return b


def _filter_by_release_date(movie: Any) -> bool:
    try:
        release_date = date.fromisoformat(movie["release_date"])
    except KeyError:
        return False

    diff = date.today() - release_date

    return diff <= timedelta(days=90)


def _find_movie_by_title_year(title: str, year: int) -> dict | None:
    match = None

    for search_year in _get_year_variants(year):
        for search_query in _get_title_variants(title):
            page = 1

            while page == 1 or page <= int(_search_api.total_pages):
                results = _search_api.movies(
                    {"query": search_query, "year": search_year, "page": page}
                )
                page += 1

                for option in results:
                    match = _best_match(option, match, search_query, search_year)

            if match:
                match = dict(match)
                match["imdb_id"] = _movie_api.external_ids(match["id"]).imdb_id

                logging.info(
                    'Matched "{title}" ({year}) against "{imdb_id}".'.format(
                        imdb_id=match["imdb_id"],
                        title=title,
                        year=year,
                    )
                )

                return match

    logging.exception(
        'Unable to find a match for "{title}" ({year}).'.format(title=title, year=year)
    )

    return None


def _get_rotten_tomatoes_movies() -> Iterator[tuple[str, int]]:
    response = requests.get(
        "https://editorial.rottentomatoes.com/guide/popular-movies/",
    )
    body = BeautifulSoup(response.content, features="html.parser")

    if body.find("h1").text != "30 Most Popular Movies Right Now":
        raise ValueError("Unable to parse Rotten Tomatoes response.")

    for movie in body.select(".article_movie_title h2"):
        title = movie.find("a").text.encode("iso-8859-1").decode("utf8")

        if not title:
            continue

        year = int(movie.find(class_="start-year").text[1:5])

        yield title, year


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
        [
            _find_movie_by_title_year(title, year)
            for title, year in _get_rotten_tomatoes_movies()
        ],
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
