#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Trusts Dolby filter, validates movie titles
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
IFTTT_EVENT_NAME = "new_dolby_showtime"
SEEN_FILE = Path("seen_dolby_showtimes.json")

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
        
        for day_offset in range(21):  # Check 3 weeks (AMC/Fandango rarely post further out)
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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("🧪 Sending test notification...")
        send_notification("TEST MOVIE", "7:00p", "2026-01-14")
        print("✅ Test notification sent! Check your phone.")
    else:
        main()
