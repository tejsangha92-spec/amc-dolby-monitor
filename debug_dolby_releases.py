#!/usr/bin/env python3
"""Throwaway diagnostic: inspect the Dolby Cinema theatrical releases page."""

import json

from playwright.sync_api import sync_playwright

URL = "https://professional.dolby.com/cinema/theatrical-releases/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        print(f"Loading {URL}")
        page.goto(URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        print("=== TITLE ===")
        print(page.title())

        print("=== BODY TEXT (first 4000 chars) ===")
        text = page.inner_text('body')
        print(text[:4000])

        print("=== POTENTIAL REPEATING CARD STRUCTURE ===")
        # Look for elements that repeat with similar class names, a common
        # pattern for a list of release cards.
        info = page.evaluate(r"""
            () => {
                const counts = {};
                document.querySelectorAll('body *[class]').forEach(el => {
                    el.className.split(/\s+/).forEach(c => {
                        if (!c) return;
                        counts[c] = (counts[c] || 0) + 1;
                    });
                });
                return Object.entries(counts)
                    .filter(([c, n]) => n >= 5 && n <= 200)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 40);
            }
        """)
        for cls, n in info:
            print(f"{n:4d}  {cls}")

        browser.close()


if __name__ == "__main__":
    main()
