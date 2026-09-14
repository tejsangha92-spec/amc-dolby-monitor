#!/usr/bin/env python3
"""Throwaway: validate scrape_rt_score() against real movies, in isolation
from the production run (no shared cache touched)."""

from playwright.sync_api import sync_playwright

import check_showtimes as cs

TEST_MOVIES = [
    "Dune: Part Two (2024)",
    "Spider-Man: Brand New Day (2026)",
    "The Odyssey (2026)",
    "PAW Patrol: The Dino Movie (2026)",
    "Idiots (2026)",
    "Not A Real Movie Title Xyz (2026)",
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        for movie in TEST_MOVIES:
            score = cs.scrape_rt_score(movie, page)
            print(f"{movie!r} -> {score}")
        browser.close()


if __name__ == "__main__":
    main()
