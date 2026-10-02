#!/usr/bin/env python3
"""Throwaway diagnostic: dump raw (unfiltered) Dolby-tab movie titles from
today's Fandango listing, to see why 'Training Day' isn't being picked up
by is_valid_movie_title()."""

from datetime import datetime
from playwright.sync_api import sync_playwright

FANDANGO_THEATER_ID = "aavib"


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
    print(f"URL: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        dolby_clicked = False
        for selector in ['text="Dolby Cinema"', 'text="DOLBY CINEMA"']:
            try:
                tab = page.locator(selector).first
                if tab.is_visible(timeout=1000):
                    tab.click()
                    page.wait_for_timeout(2000)
                    dolby_clicked = True
                    print(f"Dolby filter clicked via selector: {selector}")
                    break
            except Exception as e:
                print(f"  selector {selector} failed: {e}")
        print(f"dolby_clicked = {dolby_clicked}")

        raw = page.evaluate(r"""
            () => {
                const isVisible = (el) => {
                    const style = getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
                };
                const out = [];
                for (const movieEl of document.querySelectorAll('li.shared-movie-showtimes')) {
                    const titleEl = movieEl.querySelector('.shared-movie-showtimes__movie-title-link');
                    if (!titleEl) continue;
                    const title = titleEl.textContent.trim();
                    const visible = isVisible(movieEl);
                    const btnTexts = Array.from(movieEl.querySelectorAll('.showtime-btn')).map(b => b.textContent.trim());
                    out.push({title, visible, btnTexts});
                }
                return out;
            }
        """)
        print(f"\nFound {len(raw)} movie blocks in DOM (visible or not):")
        for item in raw:
            print(f"  title={item['title']!r} visible={item['visible']} times={item['btnTexts']}")

        browser.close()


if __name__ == "__main__":
    main()
