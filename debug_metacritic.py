#!/usr/bin/env python3
"""Throwaway diagnostic: inspect Metacritic's search page for a movie title."""

import json

from playwright.sync_api import sync_playwright

TITLES = ["Dune", "Resident Evil", "Practical Magic 2"]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        for title in TITLES:
            url = f"https://www.metacritic.com/search/{title.replace(' ', '%20')}/"
            print(f"=== {title} -> {url} ===")
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                print("Final URL:", page.url)
                print("Page title:", page.title())

                links = page.evaluate(r"""
                    () => {
                        const prefix = 'https://www.metacritic.com/movie/';
                        const anchors = Array.from(document.querySelectorAll('a[href*="/movie/"]'));
                        const seen = new Set();
                        const out = [];
                        for (const a of anchors) {
                            if (a.href.length <= prefix.length) continue;
                            if (seen.has(a.href)) continue;
                            seen.add(a.href);
                            out.push({href: a.href, text: a.textContent.trim().slice(0, 80)});
                        }
                        return out;
                    }
                """)
                print(f"Found {len(links)} movie-detail links:")
                for l in links[:15]:
                    print(json.dumps(l))

                body_len = page.evaluate("document.body.innerText.length")
                print("Body text length:", body_len)
            except Exception as e:
                print("ERROR:", e)
            print()

        browser.close()


if __name__ == "__main__":
    main()
