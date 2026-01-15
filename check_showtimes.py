#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Uses Fandango's Dolby Cinema filter tab
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
        
        for day_offset in range(28):  # Check 4 weeks
            date = datetime.now() + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
            
            print(f"  Checking {date_str}...")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                # Click the "DOLBY CINEMA" filter tab
                dolby_tab_clicked = False
                try:
                    # Try multiple selectors for the Dolby Cinema tab
                    dolby_selectors = [
                        'text="DOLBY CINEMA"',
                        'text="Dolby Cinema"',
                        '[data-format="dolby"]',
                        'button:has-text("DOLBY")',
                        'a:has-text("DOLBY")',
                        '[class*="format"]:has-text("DOLBY")',
                    ]
                    
                    for selector in dolby_selectors:
                        try:
                            dolby_tab = page.locator(selector).first
                            if dolby_tab.is_visible(timeout=2000):
                                dolby_tab.click()
                                dolby_tab_clicked = True
                                page.wait_for_timeout(2000)  # Wait for filter to apply
                                if day_offset == 0:
                                    print(f"    ✓ Clicked Dolby filter using: {selector}")
                                break
                        except:
                            continue
                except Exception as e:
                    if day_offset == 0:
                        print(f"    Could not click Dolby tab: {e}")
                
                if not dolby_tab_clicked and day_offset == 0:
                    print("    ⚠ Dolby tab not found - will parse all content")
                
                # Get filtered page content
                full_text = page.inner_text('body')
                
                # Debug on first day
                if day_offset == 0:
                    print(f"\n--- PAGE AFTER DOLBY FILTER (first 3000 chars) ---")
                    print(full_text[:3000])
                    print(f"--- END ---\n")
                
                # Check for "no showtimes" message
                if 'no showtimes' in full_text.lower() or 'no movies' in full_text.lower():
                    continue
                
                # Parse movies and times from the filtered results
                # Since we clicked Dolby filter, ALL movies shown should be Dolby
                lines = full_text.split('\n')
                current_movie = None
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Movie title pattern: "Movie Name (Year)"
                    movie_match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
                    if movie_match:
                        current_movie = line
                        continue
                    
                    # Time pattern: "6:00p" or "9:00p" etc
                    if current_movie:
                        # Match standalone times (not part of runtime like "1 hr 50 min")
                        times = re.findall(r'\b(\d{1,2}:\d{2}[ap])\b', line.lower())
                        
                        for t in times:
                            showtime = {
                                'movie': current_movie,
                                'date': date_str,
                                'time': t,
                            }
                            dolby_showtimes.append(showtime)
                            print(f"    🎬 {current_movie} at {t}")
                
            except Exception as e:
                print(f"    Error: {e}")
        
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
