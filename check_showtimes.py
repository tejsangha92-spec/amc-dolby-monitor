#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Trusts Dolby filter, validates movie titles
"""

import html
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
IFTTT_EVENT_NAME = "new_dolby_showtime"
SEEN_FILE = Path("seen_dolby_showtimes.json")
SITE_DIR = Path("docs")

THEATER_NAME = "AMC DINE-IN Thousand Oaks 14"
FANDANGO_THEATER_ID = "aavib"
AMC_THEATER_URL = "https://www.amctheatres.com/movie-theatres/los-angeles/amc-thousand-oaks-14/showtimes"


def is_valid_movie_title(title):
    """Check if this looks like a real movie title, not page navigation text."""
    # Must have year in parens
    if not re.search(r'\(\d{4}\)$', title):
        return False
    
    # Filter out obvious non-movies
    invalid_patterns = [
        'calendar', 'selected', 'previous', 'next', 
        'skip to', 'go to', 'today', 'tomorrow',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        'offers', 'gift card', 'sign in', 'join', 'theater info',
    ]
    
    title_lower = title.lower()
    for pattern in invalid_patterns:
        if pattern in title_lower:
            return False
    
    # Must be reasonable length
    name_part = re.sub(r'\s*\(\d{4}\)$', '', title)
    if len(name_part) < 2 or len(name_part) > 100:
        return False
    
    return True


def get_dolby_showtimes():
    from playwright.sync_api import sync_playwright
    
    dolby_showtimes = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        for day_offset in range(60):  # Check 2 months
            date = datetime.now() + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
            
            print(f"  Checking {date_str}...", end="")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                # Click Dolby Cinema filter
                dolby_clicked = False
                for selector in ['text="Dolby Cinema"', 'text="DOLBY CINEMA"']:
                    try:
                        tab = page.locator(selector).first
                        if tab.is_visible(timeout=1000):
                            tab.click()
                            page.wait_for_timeout(2000)
                            dolby_clicked = True
                            print(" ✓ Dolby filter clicked", end="")
                            break
                    except:
                        continue
                
                if not dolby_clicked:
                    print(" no Dolby filter")
                    continue
                
                # Walk the DOM directly so we can read each showtime button's
                # available/restricted state, not just its visible text.
                day_results = page.evaluate(r"""
                    () => {
                        const isVisible = (el) => {
                            const style = getComputedStyle(el);
                            return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
                        };
                        const results = [];
                        for (const movieEl of document.querySelectorAll('li.shared-movie-showtimes')) {
                            if (!isVisible(movieEl)) continue;
                            const titleEl = movieEl.querySelector('.shared-movie-showtimes__movie-title-link');
                            if (!titleEl) continue;
                            const title = titleEl.textContent.trim();
                            for (const btn of movieEl.querySelectorAll('.showtime-btn')) {
                                if (!isVisible(btn)) continue;
                                const text = btn.textContent.trim();
                                if (!/^\d{1,2}:\d{2}\s*[ap]/i.test(text)) continue;
                                results.push({
                                    movie: title,
                                    time: text,
                                    available: btn.className.includes('showtime-btn--available'),
                                });
                            }
                        }
                        return results;
                    }
                """)

                day_count = 0
                for item in day_results:
                    if not is_valid_movie_title(item['movie']):
                        continue
                    t_match = re.match(r'(\d{1,2}:\d{2})\s*([ap])', item['time'], re.I)
                    if not t_match:
                        continue
                    showtime = {
                        'movie': item['movie'],
                        'date': date_str,
                        'time': f"{t_match.group(1)}{t_match.group(2).lower()}",
                        'available': item['available'],
                    }
                    dolby_showtimes.append(showtime)
                    day_count += 1

                if day_count > 0:
                    print(f" → {day_count} showtimes")
                else:
                    print(" → no showtimes found")
                
            except Exception as e:
                print(f" Error: {e}")
        
        browser.close()
    
    # Deduplicate
    seen = set()
    unique = []
    for st in dolby_showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            seen.add(key)
            unique.append(st)
    
    return unique


def send_notification(movie, time, date):
    if not IFTTT_WEBHOOK_KEY:
        print(f"  [DRY RUN] {movie} - {date} {time}")
        return

    url = f"https://maker.ifttt.com/trigger/{IFTTT_EVENT_NAME}/with/key/{IFTTT_WEBHOOK_KEY}"
    try:
        resp = requests.post(url, json={
            "value1": movie,
            "value2": f"{date} at {time}",
            "value3": THEATER_NAME
        }, timeout=10)

        if resp.status_code == 200:
            print(f"  ✅ Notified: {movie} - {time}")
    except Exception as e:
        print(f"  ❌ Error: {e}")


def _time_sort_key(t):
    hour, minute, period = re.match(r'(\d{1,2}):(\d{2})([ap])', t).groups()
    hour = int(hour) % 12
    if period == 'p':
        hour += 12
    return hour, int(minute)


def _format_time(t):
    hour, minute = _time_sort_key(t)
    period = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {period}"


def build_site_html(showtimes, generated_at, new_keys=frozenset()):
    by_date = {}
    for st in showtimes:
        by_date.setdefault(st['date'], {}).setdefault(st['movie'], []).append(st)

    def chip(st):
        is_new = f"{st['movie']}|{st['date']}|{st['time']}" in new_keys
        avail_cls = "available" if st.get('available') else "restricted"
        badge = '<span class="badge">NEW</span>' if is_new else ""
        return f'<span class="chip {avail_cls}">{badge}{_format_time(st["time"])}</span>'

    date_cards = []
    for date_str in sorted(by_date):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        movies = by_date[date_str]
        movie_rows = []
        for movie in sorted(movies, key=lambda m: min(_time_sort_key(s['time']) for s in movies[m])):
            sts = sorted(movies[movie], key=lambda s: _time_sort_key(s['time']))
            time_chips = "".join(chip(s) for s in sts)
            movie_rows.append(
                f'<div class="movie"><div class="movie-name">{html.escape(movie)}</div>'
                f'<div class="times">{time_chips}</div></div>'
            )
        date_cards.append(
            f'<section class="day">'
            f'<h2>{date_obj.strftime("%A, %B %-d")}</h2>'
            f'{"".join(movie_rows)}'
            f'</section>'
        )

    body = "".join(date_cards) if date_cards else '<p class="empty">No Dolby Cinema showtimes currently listed.</p>'

    new_items = sorted(
        (st for st in showtimes if f"{st['movie']}|{st['date']}|{st['time']}" in new_keys),
        key=lambda st: (st['date'], _time_sort_key(st['time']))
    )
    banner = ""
    if new_items:
        rows = "".join(
            f'<div class="new-row"><span class="new-movie">{html.escape(st["movie"])}</span>'
            f'<span class="new-when">{datetime.strptime(st["date"], "%Y-%m-%d").strftime("%a %b %-d")} '
            f'· {_format_time(st["time"])}</span></div>'
            for st in new_items
        )
        banner = (
            f'<section class="banner"><h2>🆕 Just added ({len(new_items)})</h2>{rows}</section>'
        )

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dolby Cinema Showtimes — {html.escape(THEATER_NAME)}</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f7f7f8; --card: #ffffff; --text: #1a1a1a; --muted: #6b6b6f;
    --accent: #7c3aed; --chip-bg: #efe9fc; --border: #e6e6e9;
    --new-bg: #dcfce7; --new-text: #15803d; --new-card: #f0fdf4; --new-border: #bbf7d0;
    --avail-bg: #e36600; --avail-text: #ffffff;
    --restricted-bg: #e5e7eb; --restricted-text: #6b7280;
    --badge-bg: rgba(255, 255, 255, 0.92); --badge-text: #111827;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #131316; --card: #1c1c20; --text: #f2f2f3; --muted: #a0a0a6;
      --accent: #b394f5; --chip-bg: #2a2333; --border: #2c2c31;
      --new-bg: #14532d; --new-text: #86efac; --new-card: #142018; --new-border: #1e3a26;
      --avail-bg: #f2790a; --avail-text: #17110a;
      --restricted-bg: #2c2c31; --restricted-text: #8a8a90;
      --badge-bg: rgba(0, 0, 0, 0.55); --badge-text: #ffffff; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  header {{ padding: 32px 20px 16px; max-width: 720px; margin: 0 auto; }}
  header h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  .amc-link {{ display: inline-block; margin-top: 10px; font-size: 0.85rem; color: var(--accent);
    text-decoration: none; font-weight: 600; }}
  .amc-link:hover {{ text-decoration: underline; }}
  header .sub {{ color: var(--muted); font-size: 0.9rem; }}
  main {{ max-width: 720px; margin: 0 auto; padding: 8px 20px 60px; display: grid; gap: 16px; }}
  .day {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; }}
  .day h2 {{ margin: 0 0 12px; font-size: 1.05rem; color: var(--accent); }}
  .movie {{ padding: 10px 0; border-top: 1px solid var(--border); }}
  .movie:first-of-type {{ border-top: none; padding-top: 0; }}
  .movie-name {{ font-weight: 600; margin-bottom: 6px; }}
  .times {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{ font-size: 0.85rem; font-weight: 600; padding: 4px 10px; border-radius: 999px;
    display: inline-flex; align-items: center; gap: 5px; }}
  .chip.available {{ background: var(--avail-bg); color: var(--avail-text); }}
  .chip.restricted {{ background: var(--restricted-bg); color: var(--restricted-text);
    font-weight: 500; opacity: 0.85; }}
  .badge {{ background: var(--badge-bg); color: var(--badge-text); font-size: 0.65rem;
    font-weight: 700; letter-spacing: 0.03em; padding: 1px 5px; border-radius: 999px; }}
  .legend {{ display: flex; gap: 14px; margin-top: 10px; font-size: 0.8rem; color: var(--muted); }}
  .legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
  .legend i {{ width: 9px; height: 9px; border-radius: 999px; display: inline-block; }}
  .legend i.available {{ background: var(--avail-bg); }}
  .legend i.restricted {{ background: var(--restricted-bg); }}
  .banner {{ background: var(--new-card); border: 1px solid var(--new-border); border-radius: 12px;
    padding: 18px 20px; }}
  .banner h2 {{ margin: 0 0 12px; font-size: 1.05rem; color: var(--new-text); }}
  .new-row {{ display: flex; justify-content: space-between; gap: 12px; padding: 6px 0;
    font-size: 0.9rem; }}
  .new-movie {{ font-weight: 600; }}
  .new-when {{ color: var(--muted); white-space: nowrap; }}
  .empty {{ text-align: center; color: var(--muted); padding: 40px 0; }}
  footer {{ max-width: 720px; margin: 0 auto; padding: 0 20px 40px; color: var(--muted); font-size: 0.8rem; }}
</style>
</head>
<body>
<header>
  <h1>🎬 Dolby Cinema Showtimes</h1>
  <div class="sub">{html.escape(THEATER_NAME)} · updated {generated_at.strftime("%b %-d, %Y at %-I:%M %p UTC")}</div>
  <div class="legend"><span><i class="available"></i>Tickets on sale</span><span><i class="restricted"></i>Not yet available</span></div>
  <a class="amc-link" href="{AMC_THEATER_URL}" target="_blank" rel="noopener">View all showtimes on AMC Theatres →</a>
</header>
<main>
{banner}
{body}
</main>
<footer>Auto-generated hourly from Fandango. Runtimes/times as listed by the theater; always double-check before heading out.</footer>
</body>
</html>
'''


def load_seen():
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE) as f:
                data = json.load(f)
                cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                return {k: v for k, v in data.items() if v.get("date", "") >= cutoff}
        except:
            pass
    return {}


def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f, indent=2)


def main():
    print(f"\n{'='*50}")
    print(f"AMC Dolby Monitor")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Theater: {THEATER_NAME}")
    print(f"{'='*50}")
    
    seen = load_seen()
    print(f"\n📋 {len(seen)} previously seen showtimes")
    
    print(f"\n🔍 Checking Fandango for Dolby Cinema showtimes...")
    showtimes = get_dolby_showtimes()
    
    print(f"\n📽️  Found {len(showtimes)} unique Dolby showtimes\n")
    
    new_count = 0
    new_keys = set()
    for st in showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            new_count += 1
            new_keys.add(key)
            print(f"🎬 NEW: {st['movie']} - {st['date']} {st['time']}")
            send_notification(st['movie'], st['time'], st['date'])
            seen[key] = {"date": st['date'], "added": datetime.now().isoformat()}

    if new_count == 0:
        if len(showtimes) == 0:
            print("✓ No Dolby showtimes currently listed")
        else:
            print("✓ No NEW Dolby showtimes (all already seen)")
    else:
        print(f"\n🎉 {new_count} new showtimes!")
    
    save_seen(seen)
    print(f"\n💾 Cache saved ({len(seen)} total)")

    SITE_DIR.mkdir(exist_ok=True)
    site_html = build_site_html(showtimes, datetime.now(), new_keys)
    (SITE_DIR / "index.html").write_text(site_html, encoding="utf-8")
    print(f"🌐 Website updated ({len(showtimes)} showtimes, {len(new_keys)} new) → {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("🧪 Sending test notification...")
        send_notification("TEST MOVIE", "7:00p", "2026-01-14")
        print("✅ Test notification sent! Check your phone.")
    else:
        main()
