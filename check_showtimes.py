#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Navigate through site properly
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
THEATER_PAGE = "https://www.amctheatres.com/movie-theatres/los-angeles/amc-dine-in-thousand-oaks-14"


def get_dolby_showtimes():
    from playwright.sync_api import sync_playwright
    
    dolby_showtimes = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        try:
            # Step 1: Go to the theater's main page first
            print(f"Step 1: Loading theater page...")
            page.goto(THEATER_PAGE, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # Step 2: Click on "Showtimes" or find showtimes section
            print(f"Step 2: Looking for showtimes...")
            
            # Try clicking the showtimes tab/link if it exists
            try:
                showtimes_link = page.locator('a:has-text("Showtimes")').first
                if showtimes_link.is_visible():
                    showtimes_link.click()
                    page.wait_for_timeout(3000)
            except:
                pass
            
            # Get the page content
            page.wait_for_timeout(2000)
            full_text = page.inner_text('body')
            
            print(f"\n--- PAGE TEXT (first 3000 chars) ---")
            print(full_text[:3000])
            print(f"--- END PAGE TEXT ---\n")
            print(f"Total page length: {len(full_text)} chars\n")
            
            # Check for Dolby content
            if 'dolby' in full_text.lower():
                print("✅ Found 'Dolby' mentioned on page!")
                
                # Try to find movie sections with Dolby
                lines = full_text.split('\n')
                
                current_movie = None
                for i, line in enumerate(lines):
                    line = line.strip()
                    
                    # Skip empty lines
                    if not line:
                        continue
                    
                    # Look for Dolby Cinema mentions
                    if 'dolby cinema' in line.lower() or 'dolby' in line.lower():
                        # Look backwards for movie name
                        for j in range(i-1, max(0, i-10), -1):
                            candidate = lines[j].strip()
                            if candidate and len(candidate) > 3:
                                # Skip format/time indicators
                                if not any(x in candidate.lower() for x in ['dolby', 'imax', 'digital', 'prime', 'reserve', 'standard', 'am', 'pm', ':']):
                                    if not candidate.startswith(('$', '•', '-')):
                                        current_movie = candidate
                                        break
                        
                        # Look for times nearby
                        context_start = max(0, i-2)
                        context_end = min(len(lines), i+5)
                        context = '\n'.join(lines[context_start:context_end])
                        
                        times = re.findall(r'(\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?)', context)
                        
                        if current_movie and times:
                            for time in times:
                                print(f"  Found: {current_movie} at {time}")
                                dolby_showtimes.append({
                                    'movie': current_movie,
                                    'date': datetime.now().strftime("%Y-%m-%d"),
                                    'time': time,
                                })
            else:
                print("❌ No 'Dolby' found on page")
                
                # Check what we did find
                if 'showtimes' in full_text.lower():
                    print("  (But 'showtimes' IS on the page)")
                if len(full_text) < 1000:
                    print(f"  ⚠️ Page seems short ({len(full_text)} chars)")
                    
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
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
