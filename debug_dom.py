#!/usr/bin/env python3
"""Throwaway diagnostic: dump styling info for showtime elements on Fandango's page."""

import json
import sys
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

FANDANGO_THEATER_ID = "aavib"


def main():
    offset = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    date = datetime.now() + timedelta(days=offset)
    date_str = date.strftime("%Y-%m-%d")
    url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        print(f"Loading {url}")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        for selector in ['text="Dolby Cinema"', 'text="DOLBY CINEMA"']:
            try:
                tab = page.locator(selector).first
                if tab.is_visible(timeout=1000):
                    tab.click()
                    page.wait_for_timeout(2000)
                    print(f"Clicked Dolby filter via {selector}")
                    break
            except Exception:
                continue

        results = page.evaluate(r"""
            () => {
                const timeRe = /^\d{1,2}:\d{2}\s*[ap]\.?m?\.?$/i;
                const titleRe = /\(\d{4}\)$/;
                const nodes = Array.from(document.querySelectorAll('body *'));

                const btn = nodes
                    .filter(el => el.children.length === 0 && timeRe.test(el.textContent.trim()))
                    .slice(0, 10)
                    .map(el => {
                        const chain = [];
                        let cur = el;
                        for (let i = 0; i < 8 && cur; i++) {
                            chain.push({tag: cur.tagName, class: cur.className, id: cur.id || null});
                            cur = cur.parentElement;
                        }
                        return {
                            kind: 'showtime',
                            text: el.textContent.trim(),
                            class: el.className,
                            ancestorChain: chain,
                        };
                    });

                const titles = nodes
                    .filter(el => el.children.length === 0 && titleRe.test(el.textContent.trim()))
                    .slice(0, 10)
                    .map(el => {
                        const chain = [];
                        let cur = el;
                        for (let i = 0; i < 8 && cur; i++) {
                            chain.push({tag: cur.tagName, class: cur.className, id: cur.id || null});
                            cur = cur.parentElement;
                        }
                        return {
                            kind: 'title',
                            text: el.textContent.trim(),
                            class: el.className,
                            ancestorChain: chain,
                        };
                    });

                return {btn, titles};
            }
        """)

        print(f"Found {len(results['btn'])} showtime elements, {len(results['titles'])} title elements")
        for r in results['titles']:
            print(json.dumps(r))
        for r in results['btn']:
            print(json.dumps(r))

        browser.close()


if __name__ == "__main__":
    main()
