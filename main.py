import json
import re
from datetime import date

import requests
from bs4 import BeautifulSoup
from tmdbv3api import Movie


def generate():
    response = requests.get("https://editorial.rottentomatoes.com/guide/popular-movies/")
    body = BeautifulSoup(response.content, features="html.parser")

    if body.find("h1").text != "30 Most Popular Movies Right Now":
        raise ValueError("Rotten Tomatoes has likely changed their DOM tree.")

    replace = re.compile(r"\(.*\)")
    movies = set([])
    api = Movie()
    api.language = "en"

    for movie in body.select('.article_movie_title h2'):
        title = movie.find("a").text.encode("iso-8859-1").decode("utf8")
        year = int(movie.find(class_="start-year").text[1:5])
        match = None

        for term in [title, replace.sub("", title).rstrip()]:
            for option in api.search(term):
                if match is None:
                    match = option
                    continue

                if match.title == term and option.title != term:
                    continue

                if match.title != term and option.title == term:
                    match = option
                    continue

                if match.release_date != '' and option.release_date != '':
                    match_date = date.fromisoformat(match.release_date)
                    option_date = date.fromisoformat(option.release_date)

                    if abs(match_date.year - year) > abs(option_date.year - year):
                        match = option
                        continue

                    if abs(option_date.year - year) > abs(match_date.year - year):
                        continue

                if option.popularity > match.popularity:
                    match = option
                    continue

            if match:
                break

        if not match:
            raise ValueError(f'Unable to find a match for "{title}"')

        movies.add(match)

    if len(movies) != 30:
        raise ValueError("Unable to find 30 movies in total")

    result = []

    for movie in movies:
        result.append({
            "title": movie.title,
            "imdb_id": api.external_ids(movie.id).imdb_id,
            "poster_url": f"https://image.tmdb.org/t/p/w500{movie.poster_path}",
        })

    result = sorted(result, key=lambda x: x['imdb_id'])

    print(json.dumps(result, indent=4))


if __name__ == '__main__':
    generate()
