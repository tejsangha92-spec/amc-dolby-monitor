#!/usr/bin/env python3
"""Throwaway diagnostic: compare our hardcoded (old) slug
'amc-dine-in-thousand-oaks-14-aavib' against the current real slug
'amc-thousand-oaks-14-aavib' for today's date, with the Dolby Cinema
filter applied, to see if the stale slug is silently dropping showtimes."""

from datetime import datetime
from playwright.sync_api import sync_playwright

date_str = datetime.now().strftime("%Y-%m-%d")
URLS = {
    "OLD (our hardcoded slug)": f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-aavib/theater-page?date={date_str}",
    "NEW (current real slug)": f"https://www.fandango.com/amc-thousand-oaks-14-aavib/theater-page?date={date_str}",
}


def scrape(page, url):
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    final_url = page.url

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
    return final_url, dolby_clicked, raw


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        for label, url in URLS.items():
            print(f"=== {label}: {url} ===")
            try:
                final_url, dolby_clicked, raw = scrape(page, url)
                print(f"Final URL after load: {final_url}")
                print(f"Dolby filter clicked: {dolby_clicked}")
                print(f"Movies found: {len(raw)}")
                for item in raw:
                    print(f"  {item['title']!r} -> {item['btnTexts']}")
            except Exception as e:
                print("ERROR:", e)
            print()

        browser.close()


if __name__ == "__main__":
    main()
