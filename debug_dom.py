#!/usr/bin/env python3
"""Throwaway diagnostic: dump styling info for showtime elements on Fandango's page."""

import json
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

FANDANGO_THEATER_ID = "aavib"


def main():
    date = datetime.now() + timedelta(days=1)
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
                const nodes = Array.from(document.querySelectorAll('body *'));
                const leaves = nodes.filter(el => el.children.length === 0 && timeRe.test(el.textContent.trim()));
                return leaves.slice(0, 40).map(el => {
                    const style = getComputedStyle(el);
                    const parent = el.parentElement;
                    const pstyle = parent ? getComputedStyle(parent) : null;
                    return {
                        tag: el.tagName,
                        text: el.textContent.trim(),
                        class: el.className,
                        color: style.color,
                        bg: style.backgroundColor,
                        opacity: style.opacity,
                        pointerEvents: style.pointerEvents,
                        ariaDisabled: el.getAttribute('aria-disabled'),
                        disabled: el.disabled === true,
                        parentTag: parent ? parent.tagName : null,
                        parentClass: parent ? parent.className : null,
                        parentColor: pstyle ? pstyle.color : null,
                        parentBg: pstyle ? pstyle.backgroundColor : null,
                        href: el.tagName === 'A' ? el.href : (parent && parent.tagName === 'A' ? parent.href : null),
                    };
                });
            }
        """)

        print(f"Found {len(results)} time-like leaf elements")
        for r in results:
            print(json.dumps(r))

        browser.close()


if __name__ == "__main__":
    main()
