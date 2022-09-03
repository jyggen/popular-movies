import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

import requests
import sentry_sdk
from tmdbv3api import TV, Search

from _shared import (
    _calculate_scores,
    _sort_key,
    _get_year_variants,
    _get_title_variants,
)

_MAX_RESULTS = 6
_search_api = Search()
_tv_api = TV()


def _best_match(a: dict, b: Optional[dict], title: str, year: int) -> dict:
    if b is None:
        return a

    if a["name"] == title and b["name"] != title:
        return a

    if a["name"] != title and b["name"] == title:
        return b

    a_has_release_date = "first_air_date" in a and a["first_air_date"]
    b_has_release_date = "first_air_date" in b and b["first_air_date"]

    if a_has_release_date and not b_has_release_date:
        return a

    if not a_has_release_date and b_has_release_date:
        return b

    if a_has_release_date and b_has_release_date:
        a_date = date.fromisoformat(a["first_air_date"])
        b_date = date.fromisoformat(b["first_air_date"])

        if abs(a_date.year - year) > abs(b_date.year - year):
            return b

        if abs(a_date.year - year) < abs(b_date.year - year):
            return a

    if a["popularity"] > b["popularity"]:
        return a

    return b


def _filter_by_recently_aried(series: Any) -> bool:
    series = _tv_api.details(series["id"])

    if "last_episode_to_air" in series and series["last_episode_to_air"]:
        air_date = date.fromisoformat(series["last_episode_to_air"]["air_date"])
        diff = date.today() - air_date

        if diff <= timedelta(days=90):
            return True

    if "next_episode_to_air" in series and series["next_episode_to_air"]:
        air_date = date.fromisoformat(series["next_episode_to_air"]["air_date"])
        diff = date.today() - air_date

        if diff <= timedelta(days=90):
            return True

    return False


def _find_series_by_title_year(title: str, year: int) -> dict | None:
    match = None

    for search_year in _get_year_variants(year):
        for search_query in _get_title_variants(title):
            page = 1

            while page == 1 or page <= int(_search_api.total_pages):
                results = _search_api.tv_shows(
                    {
                        "query": search_query,
                        "first_air_date_year": search_year,
                        "page": page,
                    }
                )
                page += 1

                for option in results:
                    match = _best_match(option, match, search_query, search_year)

            if match:
                match = dict(match)
                match["imdb_id"] = _tv_api.external_ids(match["id"]).imdb_id

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


def _get_reelgood_series() -> [tuple[str, int]]:
    response = requests.get(
        "https://api.reelgood.com/v3.0/content/browse/curated/trending-picks?availability=onAnySource&content_kind=both&skip=0&sort=1&take=50"
    )

    for series in response.json()["results"]:
        if not series["released_on"]:
            continue

        yield series["title"], int(series["released_on"][0:4])


def _to_steven_lu_format(series: list[dict]) -> [dict]:
    for show in series:
        yield {
            "title": show["name"],
            "tvdb_id": _tv_api.external_ids(show["id"]).tvdb_id,
            "poster_url": f"https://image.tmdb.org/t/p/w500{show['poster_path']}",
        }


def _generate() -> list[dict]:
    series = filter(
        None,
        [
            _find_series_by_title_year(title, year)
            for title, year in _get_reelgood_series()
        ],
    )

    series = filter(_filter_by_recently_aried, series)
    series = _calculate_scores(list(series))
    series = sorted(series, key=lambda show: show["score"], reverse=True)
    series = _to_steven_lu_format(series[:_MAX_RESULTS])

    return sorted(series, key=lambda show: _sort_key(show["title"]))


if __name__ == "__main__":
    sentry_sdk.init(os.environ.get("SENTRY_DSN"), traces_sample_rate=1)

    with sentry_sdk.start_transaction(op="generate", name="Generate Series"):
        print(json.dumps(_generate(), indent=4))  # noqa: WPS421
