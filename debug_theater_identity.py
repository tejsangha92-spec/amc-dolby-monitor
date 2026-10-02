#!/usr/bin/env python3
"""Throwaway diagnostic: compare 'AMC Thousand Oaks 14' vs 'AMC DINE-IN
Thousand Oaks 14' - are these the same physical theater or two different
ones? And does the non-dine-in one have a Training Day Dolby showtime?"""

from datetime import datetime
from playwright.sync_api import sync_playwright

AMC_URL = "https://www.amctheatres.com/movie-theatres/los-angeles/amc-thousand-oaks-14/showtimes"


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        print("=== AMC's own site: amc-thousand-oaks-14 ===")
        try:
            page.goto(AMC_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            print("Final URL:", page.url)
            print("Page title:", page.title())
            text = page.inner_text('body')
            # Print the first chunk, which usually has the theater name/address header
            print("Body text (first 600 chars):")
            print(text[:600])
            print()
            print("Contains 'Training Day'?", 'Training Day' in text)
            print("Contains 'Dolby'?", 'Dolby' in text)
        except Exception as e:
            print("ERROR:", e)

        browser.close()


if __name__ == "__main__":
    main()
