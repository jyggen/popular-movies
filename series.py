import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Iterator, Optional

import requests
import sentry_sdk
from bs4 import BeautifulSoup
from tmdbv3api import TV, Search

from _shared import (
    _calculate_scores,
    _session,
    _sort_key,
    _get_title_variants,
)

_MAX_RESULTS = 6
_search_api = Search(session=_session)
_tv_api = TV(session=_session)


def _best_match(
    a: dict,
    b: Optional[dict],
    title: str,
    year: int | None,
    season_name: str,
    season_number: int | None,
) -> dict:
    if b is None:
        return a

    if a["name"].lower() == title.lower() and b["name"].lower() != title.lower():
        return a

    if a["name"].lower() != title.lower() and b["name"].lower() == title.lower():
        return b

    a_has_matching_season = next(
        (
            season
            for season in a["seasons"]
            if season["season_number"] == season_number
            or season["name"] == season_name
            or (
                not season["season_number"]
                and season["air_date"]
                and date.fromisoformat(season["air_date"]).year == year
            )
        ),
        None,
    )

    b_has_matching_season = next(
        (
            season
            for season in b["seasons"]
            if season["season_number"] == season_number
            or season["name"] == season_name
            or (
                not season["season_number"]
                and season["air_date"]
                and date.fromisoformat(season["air_date"]).year == year
            )
        ),
        None,
    )

    if a_has_matching_season and not b_has_matching_season:
        return a

    if not a_has_matching_season and b_has_matching_season:
        return b

    if (
        year
        and a_has_matching_season
        and a_has_matching_season["air_date"]
        and b_has_matching_season
        and b_has_matching_season["air_date"]
    ):
        a_date = date.fromisoformat(a_has_matching_season["air_date"])
        b_date = date.fromisoformat(b_has_matching_season["air_date"])

        if abs(a_date.year - year) > abs(b_date.year - year):
            return b

        if abs(a_date.year - year) < abs(b_date.year - year):
            return a

    if a["popularity"] > b["popularity"]:
        return a

    return b


def _filter_by_recently_aired(series: Any) -> bool:
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


def _remove_duplicates(series: list[dict]) -> list[dict]:
    seen = set()
    new_list = []

    for item in series:
        if item["id"] in seen:
            continue

        seen.add(item["id"])
        new_list.append(item)

    return new_list


def _find_series_by_title_year_season(
    title: str, year: int | None, season_name: str, season_number: int | None
) -> dict | None:
    match = None

    for search_query in _get_title_variants(title):
        page = 1

        while page == 1 or page <= int(_search_api.total_pages):
            results = _search_api.tv_shows(term=search_query, page=page)
            page += 1

            for option in results.results:
                option = _tv_api.details(option["id"])
                match = _best_match(
                    option, match, search_query, year, season_name, season_number
                )

        if match:
            match = dict(match)
            external_ids = _tv_api.external_ids(match["id"])
            match["imdb_id"] = external_ids.imdb_id
            match["tvdb_id"] = external_ids.tvdb_id

            logging.info(
                'Matched "{season_name}" of "{title}" ({year}) against "{tvdb_id}".'.format(
                    tvdb_id=match["tvdb_id"],
                    title=title,
                    season_name=season_name,
                    year=year,
                )
            )

            return match

    logging.error(
        'Unable to find a match for "{season_name}" of "{title}" ({year}).'.format(
            title=title,
            season_name=season_name,
            year=year,
        )
    )

    return None


def _get_rotten_tomatoes_series() -> Iterator[tuple[str, int | None, str, int | None]]:
    response = _session.get(
        "https://editorial.rottentomatoes.com/guide/popular-tv-shows/",
    )
    body = BeautifulSoup(response.content, features="html.parser")

    if "25 Most Popular TV Shows Right Now" not in body.find("h1").text:
        raise ValueError("Unable to parse Rotten Tomatoes response.")

    for movie in body.select(".article_movie_title h2"):
        title = movie.find("a").text

        if not title:
            continue

        parts = title.rsplit(": ", 1)
        title = parts[0]
        season_name = parts[1] if len(parts) > 1 else ""
        season = None

        if season_name.startswith("Season "):
            season = int(season_name[7:])

        yield title, None, season_name, season


def _to_steven_lu_format(series: list[dict]) -> [dict]:
    for show in series:
        yield {
            "title": show["name"],
            "tvdb_id": show["tvdb_id"],
            "poster_url": f"https://image.tmdb.org/t/p/w500{show['poster_path']}",
        }


def _generate() -> list[dict]:
    series = filter(
        None,
        [
            _find_series_by_title_year_season(title, year, season_text, season_number)
            for title, year, season_text, season_number in _get_rotten_tomatoes_series()
        ],
    )

    series = _remove_duplicates(series)
    series = filter(_filter_by_recently_aired, series)
    series = _calculate_scores(list(series))
    series = sorted(series, key=lambda show: show["score"], reverse=True)
    series = _to_steven_lu_format(series[:_MAX_RESULTS])

    return sorted(series, key=lambda show: _sort_key(show["title"]))


if __name__ == "__main__":
    sentry_sdk.init(os.environ.get("SENTRY_DSN"), traces_sample_rate=1)

    with sentry_sdk.start_transaction(op="generate", name="Generate Series"):
        print(json.dumps(_generate(), indent=4))  # noqa: WPS421
