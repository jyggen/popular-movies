import json
import re
from datetime import date, timedelta
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from tmdbv3api import Movie

_api = Movie()
_parentheses = re.compile(r"\(.*\)")


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
    if "release_date" not in movie or not movie["release_date"]:
        return False

    release_date = date.fromisoformat(movie["release_date"])
    diff = date.today() - release_date

    return diff <= timedelta(days=90)


def _find_movie_by_title_year(title: str, year: int) -> dict:
    match = None

    for term in [title, _parentheses.sub("", title).rstrip()]:
        for option in _api.search(term):
            match = _best_match(option, match, term, year)

        if match:
            return match

    raise ValueError(f'Unable to find a match for "{title}"')


def _get_rotten_tomatoes_movies() -> [tuple[str, int]]:
    response = requests.get(
        "https://editorial.rottentomatoes.com/guide/popular-movies/"
    )
    body = BeautifulSoup(response.content, features="html.parser")

    if body.find("h1").text != "30 Most Popular Movies Right Now":
        raise ValueError("Unable to parse Rotten Tomatoes")

    for movie in body.select(".article_movie_title h2"):
        title = movie.find("a").text.encode("iso-8859-1").decode("utf8")
        year = int(movie.find(class_="start-year").text[1:5])

        yield title, year


def _to_steven_lu_format(movies: list[dict]) -> [dict]:
    for movie in movies:
        yield {
            "title": movie["title"],
            "imdb_id": _api.external_ids(movie["id"]).imdb_id,
            "poster_url": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
        }


def generate():
    movies = list(
        {_find_movie_by_title_year(x, y) for x, y in _get_rotten_tomatoes_movies()}
    )

    if len(movies) != 30:
        raise ValueError("Unable to find 30 unique movies")

    movies = filter(_filter_by_release_date, movies)
    movies = sorted(movies, key=lambda x: x["popularity"], reverse=True)[0:10]
    movies = _to_steven_lu_format(movies)
    movies = sorted(list(movies), key=lambda x: x["title"])

    print(json.dumps(movies, indent=4))


if __name__ == "__main__":
    generate()
