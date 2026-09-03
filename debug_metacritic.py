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
                page.wait_for_timeout(3000)
                print("Final URL:", page.url)
                print("Page title:", page.title())

                links = page.evaluate(r"""
                    () => {
                        const anchors = Array.from(document.querySelectorAll('a[href*="/movie/"]'));
                        const seen = new Set();
                        const out = [];
                        for (const a of anchors) {
                            if (seen.has(a.href)) continue;
                            seen.add(a.href);
                            out.push({href: a.href, text: a.textContent.trim().slice(0, 80)});
                            if (out.length >= 8) break;
                        }
                        return out;
                    }
                """)
                for l in links:
                    print(json.dumps(l))
            except Exception as e:
                print("ERROR:", e)
            print()

        browser.close()


if __name__ == "__main__":
    main()
