#!/usr/bin/env python3
"""Throwaway diagnostic: inspect the Dolby Cinema theatrical releases page."""

import json
import re
from datetime import datetime

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

        text = page.inner_text('body')
        print(f"=== BODY TEXT LENGTH: {len(text)} chars ===")

        # Parse "Title \n\t Dolby Atmos? \n\t Dolby Vision? \n\t Mon DD, YYYY" blocks
        lines = [l.strip() for l in text.split('\n')]
        entries = []
        date_re = re.compile(r'^[A-Z][a-z]{2} \d{2}, \d{4}$')
        i = 0
        while i < len(lines):
            if date_re.match(lines[i]):
                # walk backwards over blank lines / format tags to find the title
                j = i - 1
                formats = []
                while j >= 0 and lines[j] in ('', 'Dolby Atmos', 'Dolby Vision', 'Dolby Cinema'):
                    if lines[j]:
                        formats.append(lines[j])
                    j -= 1
                if j >= 0 and lines[j]:
                    entries.append({'title': lines[j], 'date': lines[i], 'formats': formats})
            i += 1

        print(f"=== PARSED {len(entries)} ENTRIES ===")
        dates = [datetime.strptime(e['date'], '%b %d, %Y') for e in entries]
        if dates:
            print(f"Range: {min(dates).date()} to {max(dates).date()}")
        for e in entries:
            print(json.dumps(e))

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
