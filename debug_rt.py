#!/usr/bin/env python3
"""Throwaway diagnostic: find the real per-movie Tomatometer selector on Rotten Tomatoes."""

import json

from playwright.sync_api import sync_playwright

URL = "https://www.rottentomatoes.com/m/dune_part_two"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        page.goto(URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        print("Final URL:", page.url)
        print("Page title:", page.title())
        print()

        # 1. All distinct custom element tag names on the page.
        custom_tags = page.evaluate("""
            () => {
                const tags = new Set();
                document.querySelectorAll('*').forEach(el => {
                    if (el.tagName.includes('-')) tags.add(el.tagName.toLowerCase());
                });
                return Array.from(tags).sort();
            }
        """)
        print(f"Custom element tags ({len(custom_tags)}):")
        print(json.dumps(custom_tags))
        print()

        # 2. All distinct data-qa attribute values (RT's common test-hook convention).
        data_qa_values = page.evaluate("""
            () => {
                const vals = new Set();
                document.querySelectorAll('[data-qa]').forEach(el => vals.add(el.getAttribute('data-qa')));
                return Array.from(vals).sort();
            }
        """)
        print(f"data-qa values ({len(data_qa_values)}):")
        print(json.dumps(data_qa_values))
        print()

        # 3. Ancestor chain for each rt-text node (first 15), to see which are
        # near the hero/title area vs a carousel/widget.
        ancestor_info = page.evaluate("""
            () => {
                const out = [];
                const nodes = Array.from(document.querySelectorAll('rt-text')).slice(0, 15);
                for (const node of nodes) {
                    const chain = [];
                    let el = node;
                    for (let i = 0; i < 5 && el; i++) {
                        const attrs = [...el.attributes].map(a => `${a.name}="${a.value}"`).join(' ');
                        chain.push(`<${el.tagName.toLowerCase()} ${attrs}>`.slice(0, 150));
                        el = el.parentElement;
                    }
                    out.push({text: node.textContent.trim(), chain});
                }
                return out;
            }
        """)
        print(f"rt-text ancestor chains ({len(ancestor_info)}):")
        for info in ancestor_info:
            print(f"  text={info['text']!r}")
            for c in info['chain']:
                print(f"    {c}")
            print()

        # 4. Try schema.org JSON-LD aggregateRating specifically.
        ld_ratings = page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                    try {
                        const data = JSON.parse(s.textContent);
                        if (data.aggregateRating) out.push(data.aggregateRating);
                    } catch (e) {}
                });
                return out;
            }
        """)
        print("JSON-LD aggregateRating blocks:")
        print(json.dumps(ld_ratings, indent=2))

        browser.close()


if __name__ == "__main__":
    main()
