# Popular Movies

This tool takes the 30 most popular movies right now from Rotten Tomates and returns a subset based on their popularity on The Movie Database.

## Getting Started

### Prerequisites

- Python 3.10+
- Poetry

### Installation

```bash
poetry install
```

## Usage

```bash
env TMDB_API_KEY=<tmdb key> poetry run python main.py
```

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.

## Acknowledgements

This project is very much inspired by [sjlu/popular-movies](https://github.com/sjlu/popular-movies). The JSON file is fully compatible with the one from Steven Lu's project and should be a drop-in replacement in any application that uses it. As for the HTML page, it's also shamelessly ~~stolen from~~ based on his project.
