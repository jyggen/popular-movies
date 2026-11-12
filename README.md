# Popular Movies

This tool collects the most popular movies right now from Rotten Tomatoes, Letterboxd and The Movie Database, and returns the best of them. Each movie is ranked by its placement across the three lists combined with its Letterboxd rating. Unreleased movies and movies without a Letterboxd rating are skipped.

## Getting Started

### Prerequisites

- Python 3.14+
- uv

## Usage

```bash
env TMDB_API_KEY=<tmdb key> LETTERBOXD_API_KEY=<letterboxd key> LETTERBOXD_HOSTNAME=<letterboxd api host> uv run python main.py
```

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.

## Acknowledgements

This project is very much inspired by [sjlu/popular-movies](https://github.com/sjlu/popular-movies). The JSON file is fully compatible with the one from Steven Lu's project and should be a drop-in replacement in any application that uses it. As for the HTML page, it's also shamelessly ~~stolen from~~ based on his project.
