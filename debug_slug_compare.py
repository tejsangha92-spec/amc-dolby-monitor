#!/usr/bin/env python3
"""Throwaway diagnostic: check Fandango's Dolby-filtered listing for AMC
Thousand Oaks 14 around Oct 14, 2026 (Training Day's official Dolby
release date per our own releases scrape), dumping RAW titles (before
is_valid_movie_title filtering) to see the exact string format."""

from playwright.sync_api import sync_playwright

DATES = ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        for date_str in DATES:
            url = f"https://www.fandango.com/amc-thousand-oaks-14-aavib/theater-page?date={date_str}"
            print(f"=== {date_str}: {url} ===")
            try:
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
                            break
                    except Exception:
                        continue
                print(f"Dolby filter clicked: {dolby_clicked}")

                raw = page.evaluate(r"""
                    () => {
                        const out = [];
                        for (const movieEl of document.querySelectorAll('li.shared-movie-showtimes')) {
                            const titleEl = movieEl.querySelector('.shared-movie-showtimes__movie-title-link');
                            if (!titleEl) continue;
                            const title = titleEl.textContent.trim();
                            const btnTexts = Array.from(movieEl.querySelectorAll('.showtime-btn')).map(b => b.textContent.trim());
                            out.push({title, btnTexts});
                        }
                        return out;
                    }
                """)
                print(f"Movies found: {len(raw)}")
                for item in raw:
                    print(f"  title={item['title']!r} times={item['btnTexts']}")
            except Exception as e:
                print("ERROR:", e)
            print()

        browser.close()


if __name__ == "__main__":
    main()
