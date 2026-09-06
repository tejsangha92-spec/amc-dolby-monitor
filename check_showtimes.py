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
from urllib.parse import quote

import requests

IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
IFTTT_EVENT_NAME = "new_dolby_showtime"
SEEN_FILE = Path("seen_dolby_showtimes.json")
SITE_DIR = Path("docs")

OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "")
METASCORE_FILE = Path("metascore_cache.json")
METASCORE_REFRESH_DAYS = 7  # re-check movies we already have a score for this often
METASCORE_RECHECK_DAYS_UNSCORED = 1  # movies with no score yet: retry daily (new reviews land, cache misses get fixed)

THEATER_NAME = "AMC DINE-IN Thousand Oaks 14"
FANDANGO_THEATER_ID = "aavib"
AMC_THEATER_URL = "https://www.amctheatres.com/movie-theatres/los-angeles/amc-thousand-oaks-14/showtimes"
DOLBY_RELEASES_URL = "https://professional.dolby.com/cinema/theatrical-releases/"


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


def load_metascores():
    if METASCORE_FILE.exists():
        try:
            with open(METASCORE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_metascores(cache):
    with open(METASCORE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


_RERELEASE_SUFFIX_RE = re.compile(
    r':\s*(\d+(st|nd|rd|th)\s+anniversary|anniversary\s+edition|'
    r"director'?s\s+cut|remaster(ed)?|special\s+edition|extended\s+edition|"
    r're-?release|reissue)\b.*$',
    re.IGNORECASE,
)


def fetch_metascore(movie):
    """Look up a Metacritic score (0-100) for a movie via OMDb. None if unknown.

    Tries the exact title/year first. If that comes up empty, loosens the
    year (Fandango's listed year sometimes differs from OMDb's, e.g. for
    festival titles) and strips known re-release/edition suffixes (e.g.
    "Cars: 20th Anniversary" -> "Cars", since it's the same film and shares
    its review score) before giving up.
    """
    match = re.match(r'^(.+?)\s*\((\d{4})\)$', movie)
    title, year = (match.group(1), match.group(2)) if match else (movie, None)

    titles_to_try = [title]
    stripped = _RERELEASE_SUFFIX_RE.sub('', title).strip()
    if stripped and stripped != title:
        titles_to_try.append(stripped)

    for t in titles_to_try:
        for y in ([year, None] if year else [None]):
            params = {"t": t, "apikey": OMDB_API_KEY}
            if y:
                params["y"] = y
            try:
                resp = requests.get("https://www.omdbapi.com/", params=params, timeout=10)
                data = resp.json()
            except Exception as e:
                print(f"  ⚠️  Metascore lookup failed for {movie}: {e}")
                continue
            score = data.get("Metascore")
            if score and score.isdigit():
                return int(score)

    return None


def update_metascores(movie_titles):
    """Fetch/refresh Metascores for the given movies, using a local cache to
    avoid re-querying OMDb every run. Returns {movie: score_or_None}."""
    if not OMDB_API_KEY:
        return {}

    cache = load_metascores()
    today = datetime.now().strftime("%Y-%m-%d")
    scored_cutoff = (datetime.now() - timedelta(days=METASCORE_REFRESH_DAYS)).strftime("%Y-%m-%d")
    unscored_cutoff = (datetime.now() - timedelta(days=METASCORE_RECHECK_DAYS_UNSCORED)).strftime("%Y-%m-%d")

    for movie in movie_titles:
        entry = cache.get(movie)
        if entry is None:
            needs_fetch = True
        else:
            cutoff = unscored_cutoff if entry.get("score") is None else scored_cutoff
            needs_fetch = entry.get("checked", "") < cutoff
        if needs_fetch:
            score = fetch_metascore(movie)
            cache[movie] = {"score": score, "checked": today}

    save_metascores(cache)
    return {movie: cache[movie]["score"] for movie in movie_titles if movie in cache}


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
        
        for day_offset in range(90):  # Check 3 months
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


def get_all_theater_movies():
    """All movies playing at the theater today, across every format (not just
    Dolby Cinema) — used for the "Now in Theatres" section."""
    from playwright.sync_api import sync_playwright

    date_str = datetime.now().strftime("%Y-%m-%d")
    url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"

    titles = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            raw_titles = page.evaluate(r"""
                () => {
                    const isVisible = (el) => {
                        const style = getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
                    };
                    const titles = [];
                    for (const movieEl of document.querySelectorAll('li.shared-movie-showtimes')) {
                        if (!isVisible(movieEl)) continue;
                        const titleEl = movieEl.querySelector('.shared-movie-showtimes__movie-title-link');
                        if (!titleEl) continue;
                        titles.push(titleEl.textContent.trim());
                    }
                    return titles;
                }
            """)
            titles = [t for t in raw_titles if is_valid_movie_title(t)]
        except Exception as e:
            print(f"  ⚠️  Full theater lineup lookup failed: {e}")
        browser.close()

    return sorted(set(titles))


def _parse_dolby_releases(text, today, cutoff):
    """Extract "Title / format tags / Mon DD, YYYY" blocks from the Dolby
    releases page's plain text, keeping only today..cutoff (inclusive)."""
    lines = [l.strip() for l in text.split('\n')]
    date_re = re.compile(r'^[A-Z][a-z]{2} \d{2}, \d{4}$')
    releases = []
    seen = set()
    i = 0
    while i < len(lines):
        if date_re.match(lines[i]):
            j = i - 1
            while j >= 0 and lines[j] in ('', 'Dolby Atmos', 'Dolby Vision', 'Dolby Cinema'):
                j -= 1
            if j >= 0 and lines[j]:
                try:
                    date_obj = datetime.strptime(lines[i], '%b %d, %Y').date()
                except ValueError:
                    date_obj = None
                if date_obj and today <= date_obj <= cutoff:
                    key = (lines[j], date_obj)
                    if key not in seen:
                        seen.add(key)
                        releases.append({'title': lines[j], 'date': date_obj.strftime('%Y-%m-%d')})
        i += 1

    releases.sort(key=lambda r: r['date'])
    return releases


def get_upcoming_dolby_releases(days_ahead=90):
    """Dolby's own nationwide release lineup (not specific to any one
    theater), filtered to the next `days_ahead` days."""
    from playwright.sync_api import sync_playwright

    today = datetime.now().date()
    cutoff = today + timedelta(days=days_ahead)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        try:
            page.goto(DOLBY_RELEASES_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            text = page.inner_text('body')
        except Exception as e:
            print(f"  ⚠️  Dolby releases lookup failed: {e}")
            browser.close()
            return []
        browser.close()

    return _parse_dolby_releases(text, today, cutoff)


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


def _metacritic_search_url(movie):
    title = re.sub(r'\s*\(\d{4}\)$', '', movie)
    return f"https://www.metacritic.com/search/{quote(title)}/"


def _metascore_badge(score, movie):
    if score is None:
        return ""
    cls = "score-good" if score >= 61 else ("score-mixed" if score >= 40 else "score-bad")
    url = _metacritic_search_url(movie)
    return (
        f'<a class="score {cls}" title="View on Metacritic" href="{html.escape(url)}" '
        f'target="_blank" rel="noopener">{score}</a>'
    )


def build_site_html(showtimes, generated_at, new_keys=frozenset(), metascores=None,
                     upcoming_releases=None, now_playing_titles=None):
    metascores = metascores or {}
    upcoming_releases = upcoming_releases or []
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
            score_badge = _metascore_badge(metascores.get(movie), movie)
            movie_rows.append(
                f'<div class="movie"><div class="movie-name">{html.escape(movie)}{score_badge}</div>'
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

    if now_playing_titles is None:
        today_str = generated_at.strftime("%Y-%m-%d")
        now_playing_titles = sorted({st['movie'] for st in showtimes if st['date'] == today_str})
    now_playing_section = ""
    if now_playing_titles:
        rows = "".join(
            f'<div class="now-row"><span class="now-title">{html.escape(t)}</span>'
            f'{_metascore_badge(metascores.get(t), t)}</div>'
            for t in now_playing_titles
        )
        now_playing_section = (
            f'<section class="now-playing"><h2>🎟️ Now in Theatres</h2>'
            f'<div class="now-list">{rows}</div></section>'
        )

    releases_section = ""
    if upcoming_releases:
        rows = "".join(
            f'<div class="release-row">'
            f'<span class="release-date">{datetime.strptime(r["date"], "%Y-%m-%d").strftime("%b %-d")}</span>'
            f'<span class="release-title">{html.escape(r["title"])}</span>'
            f'</div>'
            for r in upcoming_releases
        )
        releases_section = (
            f'<section class="releases">'
            f'<h2>🎬 Coming to Dolby Cinema (next 3 months)</h2>'
            f'<p class="releases-note">Dolby\'s nationwide release lineup — not every title will '
            f'necessarily play at {html.escape(THEATER_NAME)}.</p>'
            f'<div class="release-list">{rows}</div>'
            f'</section>'
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
  header {{ padding: 32px 20px 16px; max-width: 1080px; margin: 0 auto; }}
  header h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  .amc-link {{ display: inline-block; margin-top: 10px; font-size: 0.85rem; color: var(--accent);
    text-decoration: none; font-weight: 600; }}
  .amc-link:hover {{ text-decoration: underline; }}
  header .sub {{ color: var(--muted); font-size: 0.9rem; }}
  main {{ max-width: 1080px; margin: 0 auto; padding: 8px 20px 60px;
    display: grid; grid-template-columns: 1fr 300px; gap: 16px; align-items: start; }}
  .primary {{ display: grid; gap: 16px; min-width: 0; }}
  .sidebar {{ display: grid; gap: 16px; position: sticky; top: 20px; }}
  @media (max-width: 860px) {{
    main {{ grid-template-columns: 1fr; }}
    .sidebar {{ position: static; }}
  }}
  .day {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; }}
  .day h2 {{ margin: 0 0 12px; font-size: 1.05rem; color: var(--accent); }}
  .movie {{ padding: 10px 0; border-top: 1px solid var(--border); }}
  .movie:first-of-type {{ border-top: none; padding-top: 0; }}
  .movie-name {{ font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }}
  .score {{ font-size: 0.75rem; font-weight: 700; color: #fff; padding: 1px 7px; border-radius: 4px; text-decoration: none; cursor: pointer; }}
  .score:hover {{ filter: brightness(1.12); text-decoration: underline; }}
  .score-good {{ background: #54a72a; }}
  .score-mixed {{ background: #cc8a00; }}
  .score-bad {{ background: #d3312a; }}
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
  .now-playing {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; }}
  .now-playing h2 {{ margin: 0 0 6px; font-size: 1.05rem; color: var(--accent); }}
  .now-row {{ display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding: 6px 0; border-top: 1px solid var(--border); font-size: 0.9rem; }}
  .now-row:first-child {{ border-top: none; }}
  .now-title {{ font-weight: 600; }}
  .releases {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; }}
  .releases h2 {{ margin: 0 0 6px; font-size: 1.05rem; color: var(--accent); }}
  .releases-note {{ margin: 0 0 14px; font-size: 0.8rem; color: var(--muted); }}
  .release-row {{ display: flex; gap: 12px; padding: 6px 0; border-top: 1px solid var(--border);
    font-size: 0.9rem; }}
  .release-row:first-child {{ border-top: none; }}
  .release-date {{ color: var(--accent); font-weight: 600; width: 52px; flex-shrink: 0; }}
  .empty {{ text-align: center; color: var(--muted); padding: 40px 0; }}
  footer {{ max-width: 1080px; margin: 0 auto; padding: 0 20px 40px; color: var(--muted); font-size: 0.8rem; }}
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
<div class="primary">
{banner}
{body}
</div>
<aside class="sidebar">
{now_playing_section}
{releases_section}
</aside>
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

    print(f"\n🎟️  Checking full theater lineup (all formats) for Now in Theatres...")
    now_playing_titles = get_all_theater_movies()
    print(f"🎬 {len(now_playing_titles)} movies currently playing at {THEATER_NAME}")

    movie_titles = sorted(set(st['movie'] for st in showtimes) | set(now_playing_titles))
    metascores = update_metascores(movie_titles)
    if OMDB_API_KEY:
        scored = sum(1 for v in metascores.values() if v is not None)
        print(f"🏆 Metascores: {scored}/{len(movie_titles)} movies")

    print(f"\n🎬 Checking upcoming Dolby Cinema releases...")
    upcoming_releases = get_upcoming_dolby_releases()
    print(f"📅 {len(upcoming_releases)} releases in the next 3 months")

    SITE_DIR.mkdir(exist_ok=True)
    site_html = build_site_html(showtimes, datetime.now(), new_keys, metascores, upcoming_releases, now_playing_titles)
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
