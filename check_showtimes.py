#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - GitHub Actions Version
Uses Playwright to render JavaScript-heavy pages
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Configuration
IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
IFTTT_EVENT_NAME = "new_dolby_showtime"
DAYS_AHEAD = 7
SEEN_FILE = Path("seen_dolby_showtimes.json")

THEATER_NAME = "AMC DINE-IN Thousand Oaks 14"
THEATER_URL = "https://www.amctheatres.com/movie-theatres/los-angeles/amc-dine-in-thousand-oaks-14/showtimes"


def get_dolby_showtimes():
    from playwright.sync_api import sync_playwright
    
    dolby_showtimes = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for day_offset in range(DAYS_AHEAD):
            date = datetime.now() + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            url = f"{THEATER_URL}/all/{date_str}/dolby-cinema-at-amc/all"
            
            print(f"  Checking {date_str}...")
            
            try:
                page.goto(url, timeout=30000)
                page.wait_for_timeout(3000)
                content = page.content()
                
                if 'dolby' not in content.lower():
                    continue
                
                full_text = page.inner_text('body')
                sections = re.split(r'\n(?=[A-Z][A-Za-z\s:\'0-9]+\n)', full_text)
                
                for section in sections:
                    if 'dolby' in section.lower():
                        lines = section.strip().split('\n')
                        movie_name = lines[0] if lines else "Unknown"
                        times = re.findall(r'\b(\d{1,2}:\d{2}\s*[apAP][mM]?)\b', section)
                        
                        for time in times:
                            dolby_showtimes.append({
                                'movie': movie_name.strip(),
                                'date': date_str,
                                'time': time,
                            })
                            print(f"    Found: {movie_name.strip()} at {time}")
                
            except Exception as e:
                print(f"    Error: {e}")
        
        browser.close()
    
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
        else:
            print(f"  ❌ Failed: {resp.status_code}")
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
    print(f"📋 {len(seen)} previously seen\n")
    
    print(f"🔍 Checking {DAYS_AHEAD} days for Dolby showtimes...\n")
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
    
    if new_count == 0:
        print("✓ No new Dolby showtimes")
    else:
        print(f"\n🎉 {new_count} new!")
    
    save_seen(seen)
    print(f"\n💾 Saved ({len(seen)} total)")


if __name__ == "__main__":
    main()
