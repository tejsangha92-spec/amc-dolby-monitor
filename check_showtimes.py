#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Debug Version
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


def get_dolby_showtimes():
    from playwright.sync_api import sync_playwright
    
    dolby_showtimes = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Just check today's date on the main showtimes page (no filter)
        date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        
        # Try the unfiltered showtimes page first
        url = f"https://www.amctheatres.com/movie-theatres/los-angeles/amc-dine-in-thousand-oaks-14/showtimes/all/{date_str}/all/all"
        
        print(f"Loading: {url}")
        
        try:
            page.goto(url, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(5000)  # Extra 5 seconds
            
            # Get all text on page
            full_text = page.inner_text('body')
            
            print(f"\n--- PAGE TEXT (first 2000 chars) ---")
            print(full_text[:2000])
            print(f"--- END PAGE TEXT ---\n")
            
            # Check for Dolby anywhere
            if 'dolby' in full_text.lower():
                print("✅ Found 'Dolby' mentioned on page!")
                
                # Find all lines containing Dolby
                lines = full_text.split('\n')
                dolby_lines = [l.strip() for l in lines if 'dolby' in l.lower()]
                print(f"Lines with 'Dolby': {dolby_lines[:10]}")
                
                # Try to extract showtimes near Dolby mentions
                for i, line in enumerate(lines):
                    if 'dolby' in line.lower():
                        # Get surrounding context
                        start = max(0, i-5)
                        end = min(len(lines), i+10)
                        context = '\n'.join(lines[start:end])
                        
                        # Look for movie name (usually a line with title case before Dolby)
                        movie_name = "Unknown"
                        for j in range(i-1, max(0, i-6), -1):
                            candidate = lines[j].strip()
                            if candidate and len(candidate) > 3 and not candidate.startswith(('$', '•')):
                                if not any(x in candidate.lower() for x in ['dolby', 'imax', 'digital', 'select']):
                                    movie_name = candidate
                                    break
                        
                        # Find times in context
                        times = re.findall(r'(\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?)', context)
                        
                        for time in times:
                            dolby_showtimes.append({
                                'movie': movie_name,
                                'date': date_str,
                                'time': time,
                            })
                            print(f"  Found: {movie_name} at {time}")
            else:
                print("❌ No 'Dolby' found on page")
                
                # Check if page loaded at all
                if len(full_text) < 500:
                    print("⚠️ Page might not have loaded properly")
                    print(f"Page length: {len(full_text)} chars")
                
        except Exception as e:
            print(f"Error: {e}")
        
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
    print(f"AMC Dolby Monitor - DEBUG")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Theater: {THEATER_NAME}")
    print(f"{'='*50}\n")
    
    seen = load_seen()
    
    showtimes = get_dolby_showtimes()
    
    print(f"\n📽️  Found {len(showtimes)} Dolby showtimes\n")
    
    new_count = 0
    for st in showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            new_count += 1
            print(f"🎬 NEW: {st['movie']} - {st['date']} {st['time']}")
            send_notification(st['movie'], st['time'], st['date'])
            seen[key] = {"date": st['date'], "added": datetime.now().isoformat()}
    
    if new_count == 0 and len(showtimes) == 0:
        print("✓ No Dolby showtimes found")
    elif new_count == 0:
        print("✓ No NEW Dolby showtimes")
    else:
        print(f"\n🎉 {new_count} new!")
    
    save_seen(seen)


if __name__ == "__main__":
    main()
