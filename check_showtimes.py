#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Verifies each movie has Dolby label
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
            
            print(f"  Checking {date_str}...", end="")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                # Look for Dolby Cinema filter tab and click it
                dolby_clicked = False
                dolby_selectors = [
                    'button:has-text("Dolby Cinema")',
                    'a:has-text("Dolby Cinema")',
                    'text="DOLBY CINEMA"',
                    'text="Dolby Cinema"',
                ]
                
                for selector in dolby_selectors:
                    try:
                        tab = page.locator(selector).first
                        if tab.is_visible(timeout=1000):
                            tab.click()
                            page.wait_for_timeout(2000)
                            dolby_clicked = True
                            break
                    except:
                        continue
                
                if not dolby_clicked:
                    print(" no Dolby filter")
                    continue
                
                # Now find movie sections that specifically mention Dolby Cinema
                # Look for movie containers
                movie_containers = page.locator('[class*="showtime"], [class*="movie-row"], [class*="MovieRow"], section').all()
                
                found_count = 0
                for container in movie_containers:
                    try:
                        container_text = container.inner_text()
                        
                        # Must have "Dolby" in this specific container
                        if 'dolby' not in container_text.lower():
                            continue
                        
                        # Extract movie name (pattern: Movie Name (Year))
                        movie_match = re.search(r'([A-Za-z0-9][A-Za-z0-9\s:,\'\-&\.!?]+?)\s*\((\d{4})\)', container_text)
                        if not movie_match:
                            continue
                        
                        movie_name = f"{movie_match.group(1).strip()} ({movie_match.group(2)})"
                        
                        # Extract times (6:00p, 9:00p, etc)
                        times = re.findall(r'\b(\d{1,2}:\d{2}[ap])\b', container_text.lower())
                        
                        for t in times:
                            showtime = {
                                'movie': movie_name,
                                'date': date_str,
                                'time': t,
                            }
                            dolby_showtimes.append(showtime)
                            found_count += 1
                            
                    except:
                        continue
                
                # Fallback: parse page text if no containers found
                if found_count == 0:
                    full_text = page.inner_text('body')
                    
                    # Only proceed if page mentions Dolby after the filter
                    if 'dolby' not in full_text.lower():
                        print(" no Dolby content")
                        continue
                    
                    # Split into sections by looking for movie patterns
                    # Each movie section should have: Title (Year) ... Dolby ... times
                    lines = full_text.split('\n')
                    current_movie = None
                    current_section = []
                    
                    for line in lines:
                        line = line.strip()
                        
                        # New movie starts
                        movie_match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
                        if movie_match:
                            # Process previous section if it had Dolby
                            if current_movie and any('dolby' in l.lower() for l in current_section):
                                for section_line in current_section:
                                    times = re.findall(r'\b(\d{1,2}:\d{2}[ap])\b', section_line.lower())
                                    for t in times:
                                        showtime = {
                                            'movie': current_movie,
                                            'date': date_str,
                                            'time': t,
                                        }
                                        dolby_showtimes.append(showtime)
                                        found_count += 1
                            
                            # Start new section
                            current_movie = line
                            current_section = []
                        elif current_movie:
                            current_section.append(line)
                    
                    # Don't forget last section
                    if current_movie and any('dolby' in l.lower() for l in current_section):
                        for section_line in current_section:
                            times = re.findall(r'\b(\d{1,2}:\d{2}[ap])\b', section_line.lower())
                            for t in times:
                                showtime = {
                                    'movie': current_movie,
                                    'date': date_str,
                                    'time': t,
                                }
                                dolby_showtimes.append(showtime)
                                found_count += 1
                
                if found_count > 0:
                    print(f" ✓ {found_count} showtimes")
                else:
                    print(" no Dolby showtimes")
                
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
