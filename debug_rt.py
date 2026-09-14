#!/usr/bin/env python3
"""Throwaway diagnostic: inspect Rotten Tomatoes' search + movie page structure."""

import json

from playwright.sync_api import sync_playwright

SEARCH_TITLES = ["Dune Part Two", "The Odyssey", "Spider-Man Brand New Day", "PAW Patrol"]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        print("########## PHASE 1: SEARCH PAGE ##########\n")
        movie_links_by_title = {}
        for title in SEARCH_TITLES:
            url = f"https://www.rottentomatoes.com/search?search={title.replace(' ', '%20')}"
            print(f"=== {title} -> {url} ===")
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                print("Final URL:", page.url)
                print("Page title:", page.title())

                links = page.evaluate(r"""
                    () => {
                        const prefix = 'https://www.rottentomatoes.com/m/';
                        const anchors = Array.from(document.querySelectorAll('a[href*="/m/"]'));
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
                print(f"Found {len(links)} movie links:")
                for l in links[:10]:
                    print(json.dumps(l))
                if links:
                    movie_links_by_title[title] = links[0]['href']
            except Exception as e:
                print("ERROR:", e)
            print()

        print("\n########## PHASE 2: MOVIE PAGE SCORE EXTRACTION ##########\n")
        # Include a couple of known-good direct URLs in case search didn't find anything usable.
        test_urls = list(movie_links_by_title.values()) or []
        test_urls.append("https://www.rottentomatoes.com/m/dune_part_two")

        for url in dict.fromkeys(test_urls):
            print(f"=== {url} ===")
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                print("Final URL:", page.url)
                print("Page title:", page.title())

                # JSON-LD blocks that might carry aggregateRating
                ld_blocks = page.evaluate("""
                    () => Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s => s.textContent)
                """)
                for block in ld_blocks:
                    if 'ating' in block:
                        print("JSON-LD (truncated 500):", block[:500])

                # RT's web components (rt-text slots, score-icon elements)
                els = page.evaluate("""
                    () => {
                        const out = [];
                        document.querySelectorAll('rt-text').forEach(el => {
                            out.push({tag: 'rt-text', slot: el.getAttribute('slot'), text: el.textContent.trim()});
                        });
                        document.querySelectorAll('score-icon-critics, score-icon-audience, media-scorecard, rt-button').forEach(el => {
                            out.push({tag: el.tagName, attrs: [...el.attributes].map(a => `${a.name}=${a.value}`).join(' ')});
                        });
                        return out;
                    }
                """)
                print(f"Found {len(els)} score-related elements:")
                for el in els[:20]:
                    print(json.dumps(el))

                page.wait_for_timeout(2000)
                # Re-check after a short wait in case of hydration delay
                els_after_wait = page.evaluate("""
                    () => {
                        const out = [];
                        document.querySelectorAll('rt-text').forEach(el => {
                            out.push({tag: 'rt-text', slot: el.getAttribute('slot'), text: el.textContent.trim()});
                        });
                        return out;
                    }
                """)
                print(f"rt-text elements after 2s wait: {len(els_after_wait)}")
                for el in els_after_wait[:20]:
                    print(json.dumps(el))

            except Exception as e:
                print("ERROR:", e)
            print()

        browser.close()


if __name__ == "__main__":
    main()
