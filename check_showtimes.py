#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Clicks Dolby filter for reliable parsing
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
                page.wait_for_timeout(2000)
                
                # Try to click the Dolby Cinema filter
                dolby_filter_clicked = False
                try:
                    # Look for the Dolby Cinema filter button
                    dolby_btn = page.locator('text="DOLBY CINEMA"').first
                    if dolby_btn.is_visible():
                        dolby_btn.click()
                        page.wait_for_timeout(1500)
                        dolby_filter_clicked = True
                        print(f"    ✓ Clicked Dolby filter")
                except:
                    pass
                
                # Get page text after filtering
                full_text = page.inner_text('body')
                
                # Debug on first day
                if day_offset == 0:
                    print(f"\n--- PAGE AFTER FILTER (first 2500 chars) ---")
                    print(full_text[:2500])
                    print(f"--- END ---\n")
                    print(f"Total length: {len(full_text)} chars")
                
                # Check for "no showtimes" message
                if 'no showtimes' in full_text.lower() or 'no movies' in full_text.lower():
                    print(f"    No Dolby showtimes for {date_str}")
                    continue
                
                # Parse movies - after clicking filter, all shown movies should be Dolby
                if dolby_filter_clicked:
                    lines = full_text.split('\n')
                    current_movie = None
                    
                    for i, line in enumerate(lines):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Movie titles typically have year in parens and are followed by rating info
                        if re.search(r'\(\d{4}\)$', line):
                            current_movie = line
                            continue
                        
                        # Look for showtimes (format: 7:00p, 10:30p, etc)
                        if current_movie:
                            times = re.findall(r'(\d{1,2}:\d{2}[ap])', line.lower())
                            for t in times:
                                # Format time properly
                                time_str = t[:-1] + ':00 ' + ('PM' if t[-1] == 'p' else 'AM')
                                dolby_showtimes.append({
                                    'movie': current_movie,
                                    'date': date_str,
                                    'time': t,
                                })
                                print(f"    🎬 {current_movie} at {t}")
                else:
                    # No Dolby filter found - manually search for Dolby section
                    if 'dolby cinema' in full_text.lower():
                        # Find movie sections with Dolby
                        lines = full_text.split('\n')
                        current_movie = None
                        in_dolby = False
                        
                        for i, line in enumerate(lines):
                            line = line.strip()
                            if not line:
                                continue
                            
                            # Check for movie title
                            if re.search(r'\(\d{4}\)$', line):
                                current_movie = line
                                in_dolby = False
                                continue
                            
                            # Check if this movie has Dolby
                            if current_movie and 'dolby cinema' in line.lower():
                                in_dolby = True
                                continue
                            
                            # Get times if in Dolby section
                            if in_dolby and current_movie:
                                times = re.findall(r'(\d{1,2}:\d{2}[ap])', line.lower())
                                for t in times:
                                    dolby_showtimes.append({
                                        'movie': current_movie,
                                        'date': date_str,
                                        'time': t,
                                    })
                                    print(f"    🎬 {current_movie} at {t}")
                                
                                # Reset after finding times
                                if times:
                                    in_dolby = False
                            
                            # Reset if we hit another format
                            if any(f in line.lower() for f in ['standard', 'imax', 'prime', 'reald 3d']):
                                if 'dolby' not in line.lower():
                                    in_dolby = False
                
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
            "value3": ""
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
    
    print(f"\n🔍 Checking Fandango for Dolby showtimes...")
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
