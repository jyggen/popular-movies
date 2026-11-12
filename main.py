import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional, Iterator

import sentry_sdk
from bs4 import BeautifulSoup
from tmdbv3api import Movie, Search, Trending
from tmdbv3api.as_obj import AsObj

from _shared import (
    _session,
    _sort_key,
    _calculate_scores,
    _get_year_variants,
    _get_title_variants,
    _get_poster_url,
    _normalize_string,
)

_MAX_RESULTS = 15
_movie_api = Movie(session=_session)
_search_api = Search(session=_session)
_trending_api = Trending(session=_session)


def _best_match(
    a: AsObj, b: Optional[AsObj], title: str, year: int, directors: set[str]
) -> AsObj:
    if b is None:
        return a

    a_directors = {
        _normalize_string(director["name"])
        for director in a["credits"]["crew"]
        if director["job"] == "Director"
    }
    b_directors = {
        _normalize_string(director["name"])
        for director in b["credits"]["crew"]
        if director["job"] == "Director"
    }

    a_director_overlap = len(a_directors & directors)
    b_director_overlap = len(b_directors & directors)

    if a_director_overlap > 0 and b_director_overlap == 0:
        return a

    if a_director_overlap == 0 and b_director_overlap > 0:
        return b

    if a_director_overlap > b_director_overlap:
        return a

    if b_director_overlap > a_director_overlap:
        return b

    if (
        _normalize_string(a["title"]) == title
        and _normalize_string(b["title"]) != title
    ):
        return a

    if (
        _normalize_string(a["title"]) != title
        and _normalize_string(b["title"]) == title
    ):
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

    return diff <= timedelta(days=120)


def _find_movie_by_title_year_directors(
    title: str, year: int, directors: set[str]
) -> dict | None:
    directors = {_normalize_string(d) for d in directors}
    match = None
    cache = {}

    for search_year in _get_year_variants(year):
        for search_query in _get_title_variants(title):
            page = 1

            while page == 1 or page <= int(_search_api.total_pages):
                results = _search_api.movies(
                    term=search_query, year=search_year, page=page
                )
                page += 1

                if not results.total_results:
                    continue

                for option in results:
                    if option["id"] not in cache:
                        cache[option["id"]] = _movie_api.details(
                            option["id"], append_to_response="credits"
                        )

                    match = _best_match(
                        cache[option["id"]],
                        match,
                        _normalize_string(search_query),
                        search_year,
                        directors,
                    )

            if match:
                logging.info(
                    'Matched "{title}" ({year}) against "{imdb_id}".'.format(
                        imdb_id=match["imdb_id"],
                        title=title,
                        year=year,
                    )
                )

                return dict(match)

    logging.error(
        'Unable to find a match for "{title}" ({year}).'.format(title=title, year=year)
    )

    return None


def _get_letterboxd_movies() -> Iterator[dict]:
    response = _session.get(
        f"https://{os.environ["LETTERBOXD_HOSTNAME"]}/films?sort=FilmPopularityThisWeek&perPage=30",
        headers={
            "Authorization": f"Bearer {os.environ["LETTERBOXD_API_KEY"]}",
        },
    )

    response.raise_for_status()

    for movie in response.json()["items"]:
        yield _movie_api.details(next(link["id"] for link in movie["links"] if link["type"] == "tmdb"))


def _get_rotten_tomatoes_movies() -> Iterator[dict]:
    response = _session.get(
        "https://editorial.rottentomatoes.com/guide/popular-movies/",
    )

    response.raise_for_status()

    body = BeautifulSoup(response.content, features="html.parser")

    if "30 Most Popular Movies Right Now" not in body.find("h1").text:
        raise ValueError("Unable to parse Rotten Tomatoes response.")

    for movie in body.select(".block-countdown"):
        title = movie.select_one(".meta-title-wrapper a").text

        if not title:
            continue

        year = int(movie.select_one(".meta-title-wrapper span").text[1:5])
        directors = set(
            director.text for director in movie.select(".meta-detail:last-child a")
        )

        result = _find_movie_by_title_year_directors(title, year, directors)

        if result:
            yield result

def _get_tmdb_movies() -> Iterator[dict]:
    page = 1
    count = 0

    while count < 30:
        for movie in _trending_api.movie_week(page=page)["results"]:
            yield movie

            count += 1

            if count == 30:
                break

        page += 1


def _to_steven_lu_format(movies: list[dict]) -> Iterator[dict]:
    yield from (
        {
            "title": movie["title"],
            "imdb_id": movie["imdb_id"],
            "poster_url": _get_poster_url(movie["imdb_id"]),
        }
        for movie in movies
    )


def _generate() -> list[dict]:
    movies = [*_get_rotten_tomatoes_movies(), *_get_letterboxd_movies(), *_get_tmdb_movies()]
    movies = list({movie["id"]: movie for movie in movies}.values())
    movies = filter(_filter_by_release_date, _get_rotten_tomatoes_movies())
    movies = _calculate_scores(list(movies))
    movies = sorted(movies, key=lambda movie: movie["score"], reverse=True)
    movies = _to_steven_lu_format(movies[:_MAX_RESULTS])

    return sorted(movies, key=lambda movie: _sort_key(movie["title"]))


if __name__ == "__main__":
    sentry_sdk.init(os.environ.get("SENTRY_DSN"), traces_sample_rate=1)

    with sentry_sdk.start_transaction(op="generate", name="Generate Movies"):
        print(json.dumps(_generate(), indent=4))  # noqa: WPS421
