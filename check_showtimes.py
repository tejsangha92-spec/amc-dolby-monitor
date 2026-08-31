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

IFTTT_WEBHOOK_KEYS = [
    k.strip() for k in os.environ.get("IFTTT_WEBHOOK_KEYS", "").split(",") if k.strip()
]
IFTTT_EVENT_NAME = "new_dolby_showtime"
SEEN_FILE = Path("seen_dolby_showtimes.json")
SITE_DIR = Path("docs")

THEATER_NAME = "AMC DINE-IN Thousand Oaks 14"
FANDANGO_THEATER_ID = "aavib"


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
                
                # Get page text and parse movies + times
                full_text = page.inner_text('body')
                lines = full_text.split('\n')
                
                current_movie = None
                day_count = 0
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check for movie title (ends with year in parens)
                    movie_match = re.match(r'^(.+\(\d{4}\))$', line)
                    if movie_match:
                        potential_title = movie_match.group(1)
                        if is_valid_movie_title(potential_title):
                            current_movie = potential_title
                        else:
                            current_movie = None  # Reset if invalid
                        continue
                    
                    # Look for showtimes if we have a valid movie
                    if current_movie:
                        times = re.findall(r'\b(\d{1,2}:\d{2}[ap])\b', line.lower())
                        for t in times:
                            showtime = {
                                'movie': current_movie,
                                'date': date_str,
                                'time': t,
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
    if not IFTTT_WEBHOOK_KEYS:
        print(f"  [DRY RUN] {movie} - {date} {time}")
        return

    for key in IFTTT_WEBHOOK_KEYS:
        url = f"https://maker.ifttt.com/trigger/{IFTTT_EVENT_NAME}/with/key/{key}"
        try:
            resp = requests.post(url, json={
                "value1": movie,
                "value2": f"{date} at {time}",
                "value3": THEATER_NAME
            }, timeout=10)

            if resp.status_code == 200:
                print(f"  ✅ Notified ({key[:6]}...): {movie} - {time}")
        except Exception as e:
            print(f"  ❌ Error ({key[:6]}...): {e}")


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


def build_site_html(showtimes, generated_at):
    by_date = {}
    for st in showtimes:
        by_date.setdefault(st['date'], {}).setdefault(st['movie'], []).append(st['time'])

    date_cards = []
    for date_str in sorted(by_date):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        movies = by_date[date_str]
        movie_rows = []
        for movie in sorted(movies, key=lambda m: min(_time_sort_key(t) for t in movies[m])):
            times = sorted(movies[movie], key=_time_sort_key)
            time_chips = "".join(f'<span class="chip">{_format_time(t)}</span>' for t in times)
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
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #131316; --card: #1c1c20; --text: #f2f2f3; --muted: #a0a0a6;
      --accent: #b394f5; --chip-bg: #2a2333; --border: #2c2c31; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  header {{ padding: 32px 20px 16px; max-width: 720px; margin: 0 auto; }}
  header h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  header .sub {{ color: var(--muted); font-size: 0.9rem; }}
  main {{ max-width: 720px; margin: 0 auto; padding: 8px 20px 60px; display: grid; gap: 16px; }}
  .day {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; }}
  .day h2 {{ margin: 0 0 12px; font-size: 1.05rem; color: var(--accent); }}
  .movie {{ padding: 10px 0; border-top: 1px solid var(--border); }}
  .movie:first-of-type {{ border-top: none; padding-top: 0; }}
  .movie-name {{ font-weight: 600; margin-bottom: 6px; }}
  .times {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{ background: var(--chip-bg); color: var(--accent); font-size: 0.85rem;
    padding: 4px 10px; border-radius: 999px; }}
  .empty {{ text-align: center; color: var(--muted); padding: 40px 0; }}
  footer {{ max-width: 720px; margin: 0 auto; padding: 0 20px 40px; color: var(--muted); font-size: 0.8rem; }}
</style>
</head>
<body>
<header>
  <h1>🎬 Dolby Cinema Showtimes</h1>
  <div class="sub">{html.escape(THEATER_NAME)} · updated {generated_at.strftime("%b %-d, %Y at %-I:%M %p UTC")}</div>
</header>
<main>
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
    for st in showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            new_count += 1
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
    (SITE_DIR / "index.html").write_text(build_site_html(showtimes, datetime.now()), encoding="utf-8")
    print(f"🌐 Website updated ({len(showtimes)} showtimes) → {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("🧪 Sending test notification...")
        send_notification("TEST MOVIE", "7:00p", "2026-01-14")
        print("✅ Test notification sent! Check your phone.")
    else:
        main()
