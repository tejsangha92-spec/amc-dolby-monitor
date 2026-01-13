#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Stealth mode with Fandango fallback
"""

import json
import os
import re
import random
from datetime import datetime, timedelta
from pathlib import Path

import requests

IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
IFTTT_EVENT_NAME = "new_dolby_showtime"
SEEN_FILE = Path("seen_dolby_showtimes.json")

THEATER_NAME = "AMC DINE-IN Thousand Oaks 14"

# Fandango theater ID for this location
FANDANGO_THEATER_ID = "aavib"


def try_fandango():
    """Try Fandango as primary source - more reliable than AMC direct"""
    from playwright.sync_api import sync_playwright
    
    dolby_showtimes = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        # Check multiple days
        for day_offset in range(7):
            date = datetime.now() + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            # Fandango theater page
            url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
            
            print(f"  Checking Fandango {date_str}...")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                full_text = page.inner_text('body')
                
                # Debug: Show what we got on first day
                if day_offset == 0:
                    print(f"\n--- FANDANGO PAGE (first 2000 chars) ---")
                    print(full_text[:2000])
                    print(f"--- END ---\n")
                
                if 'dolby' in full_text.lower():
                    print(f"    ✅ Found Dolby content!")
                    
                    # Parse the page for Dolby showtimes
                    lines = full_text.split('\n')
                    current_movie = None
                    
                    for i, line in enumerate(lines):
                        line_lower = line.lower().strip()
                        
                        # Check if this looks like a movie title (before format info)
                        if line.strip() and len(line.strip()) > 3:
                            # Movie titles are usually standalone lines before format/time info
                            if not any(x in line_lower for x in ['dolby', 'imax', 'standard', 'premium', 'reserve', 'dine-in', 'am', 'pm', '$', 'buy', 'sold']):
                                if ':' not in line or len(line) > 30:  # Not a time
                                    current_movie = line.strip()
                        
                        # Look for Dolby Cinema format
                        if 'dolby' in line_lower:
                            # Get times from nearby lines
                            context_start = max(0, i)
                            context_end = min(len(lines), i + 8)
                            context = '\n'.join(lines[context_start:context_end])
                            
                            # Find times
                            times = re.findall(r'(\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?)', context)
                            
                            if current_movie and times:
                                for time in times[:3]:  # Limit to 3 times per section
                                    dolby_showtimes.append({
                                        'movie': current_movie,
                                        'date': date_str,
                                        'time': time.strip(),
                                    })
                                    print(f"    Found: {current_movie} at {time}")
                    
            except Exception as e:
                print(f"    Error: {e}")
        
        browser.close()
    
    return dolby_showtimes


def try_google_showtimes():
    """Fallback: Search Google for showtimes"""
    from playwright.sync_api import sync_playwright
    
    dolby_showtimes = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        search_url = "https://www.google.com/search?q=AMC+DINE-IN+Thousand+Oaks+14+dolby+cinema+showtimes"
        
        print(f"  Trying Google search...")
        
        try:
            page.goto(search_url, timeout=30000)
            page.wait_for_timeout(3000)
            
            full_text = page.inner_text('body')
            
            print(f"\n--- GOOGLE RESULTS (first 2000 chars) ---")
            print(full_text[:2000])
            print(f"--- END ---\n")
            
            if 'dolby' in full_text.lower():
                print("  ✅ Found Dolby in Google results")
                # Parse results...
                
        except Exception as e:
            print(f"  Error: {e}")
        
        browser.close()
    
    return dolby_showtimes


def get_dolby_showtimes():
    """Try multiple sources to find Dolby showtimes"""
    
    # Try Fandango first (more reliable)
    print("\n📍 Trying Fandango...")
    showtimes = try_fandango()
    
    if showtimes:
        return showtimes
    
    # Fallback to Google
    print("\n📍 Trying Google search fallback...")
    showtimes = try_google_showtimes()
    
    return showtimes


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
    
    showtimes = get_dolby_showtimes()
    
    # Deduplicate
    unique = []
    seen_keys = set()
    for st in showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(st)
    
    print(f"\n📽️  Found {len(unique)} unique Dolby showtimes\n")
    
    new_count = 0
    for st in unique:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            new_count += 1
            print(f"🎬 NEW: {st['movie']} - {st['date']} {st['time']}")
            send_notification(st['movie'], st['time'], st['date'])
            seen[key] = {"date": st['date'], "added": datetime.now().isoformat()}
    
    if new_count == 0:
        if len(unique) == 0:
            print("✓ No Dolby showtimes currently listed")
        else:
            print("✓ No NEW Dolby showtimes (all already seen)")
    else:
        print(f"\n🎉 {new_count} new showtimes!")
    
    save_seen(seen)
    print(f"\n💾 Cache saved ({len(seen)} total)")


if __name__ == "__main__":
    main()
