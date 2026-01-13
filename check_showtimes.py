#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Improved Fandango parsing
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
        
        for day_offset in range(7):
            date = datetime.now() + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
            
            print(f"  Checking {date_str}...")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                
                # Scroll down to load movie listings
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(500)
                
                # Get FULL page text
                full_text = page.inner_text('body')
                
                # Debug: Show relevant portion on first day
                if day_offset == 0:
                    # Find where movie listings start (after offers)
                    lower_text = full_text.lower()
                    
                    # Look for Dolby section
                    dolby_pos = lower_text.find('dolby')
                    if dolby_pos > 0:
                        # Show context around Dolby mention
                        start = max(0, dolby_pos - 200)
                        end = min(len(full_text), dolby_pos + 800)
                        print(f"\n--- DOLBY CONTEXT ---")
                        print(full_text[start:end])
                        print(f"--- END CONTEXT ---\n")
                    
                    print(f"Total page length: {len(full_text)} chars")
                    print(f"'dolby' appears {lower_text.count('dolby')} times")
                
                # Parse for Dolby showtimes
                if 'dolby' in full_text.lower():
                    # Split into sections - movies typically separated by blank lines or specific patterns
                    lines = full_text.split('\n')
                    
                    current_movie = None
                    in_dolby_section = False
                    
                    for i, line in enumerate(lines):
                        line_stripped = line.strip()
                        line_lower = line_stripped.lower()
                        
                        if not line_stripped:
                            continue
                        
                        # Detect if we're entering a Dolby section
                        if 'dolby cinema' in line_lower or 'dolby atmos' in line_lower:
                            in_dolby_section = True
                            
                            # Look backwards for movie name
                            for j in range(i-1, max(0, i-15), -1):
                                candidate = lines[j].strip()
                                if candidate and len(candidate) > 5:
                                    # Movie names are typically title case, not all caps
                                    # Skip common non-movie strings
                                    skip_words = ['dolby', 'imax', 'standard', 'premium', 'reserve', 
                                                  'dine-in', 'buy', 'sold', 'tickets', 'fandango',
                                                  'offers', 'screen', 'theater', 'cinema', 'movie',
                                                  'showtimes', 'today', 'tomorrow', 'select']
                                    
                                    if not any(w in candidate.lower() for w in skip_words):
                                        # Check if it looks like a time
                                        if not re.match(r'^\d{1,2}:\d{2}', candidate):
                                            current_movie = candidate
                                            break
                            
                            continue
                        
                        # If we're in a Dolby section, look for times
                        if in_dolby_section or 'dolby' in line_lower:
                            # Find times in current line and next few lines
                            context = '\n'.join(lines[i:min(len(lines), i+5)])
                            times = re.findall(r'(\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?)', context)
                            
                            if times and current_movie:
                                for time in times:
                                    showtime = {
                                        'movie': current_movie,
                                        'date': date_str,
                                        'time': time.strip(),
                                    }
                                    dolby_showtimes.append(showtime)
                                    print(f"    Found: {current_movie} at {time}")
                                
                                in_dolby_section = False  # Reset after finding times
                        
                        # Reset Dolby section if we hit another format type
                        if any(f in line_lower for f in ['standard', 'imax', 'prime', 'reald']):
                            if 'dolby' not in line_lower:
                                in_dolby_section = False
                
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
    main()
