#!/usr/bin/env python3
"""Throwaway diagnostic: list all theaters Fandango shows for Thousand Oaks,
CA, to check whether 'AMC Thousand Oaks 14' and 'AMC DINE-IN Thousand Oaks
14' are the same theater or two different ones."""

from playwright.sync_api import sync_playwright
import json

URL = "https://www.fandango.com/thousand-oaks-ca_movietimes"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        print(f"URL: {URL}")
        try:
            page.goto(URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            print("Final URL:", page.url)
            print("Page title:", page.title())

            theaters = page.evaluate(r"""
                () => {
                    const out = [];
                    const seen = new Set();
                    document.querySelectorAll('a[href*="/amc"]').forEach(a => {
                        if (seen.has(a.href)) return;
                        seen.add(a.href);
                        out.push({href: a.href, text: a.textContent.trim().slice(0, 100)});
                    });
                    return out;
                }
            """)
            print(f"\nFound {len(theaters)} AMC-related links:")
            for t in theaters:
                print(json.dumps(t))

            body_text = page.inner_text('body')
            print("\n'Thousand Oaks' mentions in body text:")
            idx = 0
            count = 0
            while count < 10:
                idx = body_text.find('Thousand Oaks', idx)
                if idx == -1:
                    break
                print(repr(body_text[max(0, idx-40):idx+40]))
                idx += 1
                count += 1
        except Exception as e:
            print("ERROR:", e)

        browser.close()


if __name__ == "__main__":
    main()
