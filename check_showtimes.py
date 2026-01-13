#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - GitHub Actions Version
Uses Fandango as data source (more reliable than scraping AMC directly)
"""

import requests
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

# Configuration from environment variables
IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
IFTTT_EVENT_NAME = "new_dolby_showtime"
DAYS_AHEAD = 14
SEEN_FILE = Path("seen_dolby_showtimes.json")

# Fandango theater ID for AMC DINE-IN Thousand Oaks 14
# Found from: https://www.fandango.com/amc-thousand-oaks-14-aavib/theater-page
FANDANGO_THEATER_ID = "aavib"


def get_dolby_showtimes(days_ahead=14):
    """Fetch Dolby showtimes from Fandango."""
    from bs4 import BeautifulSoup
    
    dolby_showtimes = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    for day_offset in range(days_ahead):
        date = datetime.now() + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")
        
        # Fandango URL pattern
        url = f"https://www.fandango.com/amc-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
        
        try:
            print(f"  Checking {date_str}...")
            response = requests.get(url, headers=headers, timeout=30)
            print(f"    Status: {response.status_code}, Length: {len(response.text)}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                page_text = response.text.lower()
                
                # Debug: Check if Dolby is mentioned anywhere
                if 'dolby' in page_text:
                    print(f"    Found 'dolby' mentioned on page")
                
                # Look for movie listings
                # Fandango uses various class patterns
                movie_items = soup.find_all(['li', 'div', 'article'], class_=lambda c: c and any(x in str(c).lower() for x in ['movie', 'film', 'showtime']) if c else False)
                print(f"    Found {len(movie_items)} potential movie items")
                
                # Method 1: Look for structured data
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get('@type') in ['ScreeningEvent', 'Movie']:
                                name = item.get('name', '') or item.get('workPresented', {}).get('name', '')
                                if name:
                                    print(f"    Found structured data: {name}")
                    except:
                        pass
                
                # Method 2: Look for Dolby-specific elements
                dolby_elements = soup.find_all(string=re.compile(r'dolby', re.I))
                for elem in dolby_elements:
                    parent = elem.find_parent(['div', 'li', 'section', 'article'])
                    if parent:
                        # Try to extract movie name and time
                        text = parent.get_text(' ', strip=True)
                        print(f"    Dolby element text: {text[:100]}...")
                        
                        # Look for time patterns
                        times = re.findall(r'\b(\d{1,2}:\d{2}\s*[apAP][mM]?)\b', text)
                        
                        # Look for movie title (usually in a heading or link)
                        title_elem = parent.find(['h2', 'h3', 'h4', 'a'])
                        movie_name = title_elem.get_text(strip=True) if title_elem else 'Unknown'
                        
                        for time in times:
                            dolby_showtimes.append({
                                'movie': movie_name,
                                'date': date_str,
                                'time': time,
                                'format': 'Dolby Cinema'
                            })
                
                # Method 3: Try to find any showtime data in page
                if not dolby_showtimes and 'dolby' in page_text:
                    # Look for showtime buttons/links
                    all_times = soup.find_all(['a', 'button'], href=lambda h: h and 'checkout' in str(h).lower() if h else False)
                    print(f"    Found {len(all_times)} checkout links")
                    
        except requests.exceptions.RequestException as e:
            print(f"    Network error: {e}")
        except Exception as e:
            print(f"    Error: {e}")
    
    # Remove duplicates
    seen_keys = set()
    unique = []
    for st in dolby_showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(st)
    
    return unique


def test_ifttt():
    """Send a test notification to verify IFTTT is working."""
    if not IFTTT_WEBHOOK_KEY:
        print("⚠️  No IFTTT key - skipping test")
        return False
    
    webhook_url = f"https://maker.ifttt.com/trigger/{IFTTT_EVENT_NAME}/with/key/{IFTTT_WEBHOOK_KEY}"
    
    payload = {
        "value1": "Test Movie",
        "value2": "Test notification - setup working!",
        "value3": ""
    }
    
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📱 IFTTT test: {resp.status_code} - {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ IFTTT test failed: {e}")
        return False


def send_notification(movie, time, date, url=""):
    """Send IFTTT webhook notification."""
    if not IFTTT_WEBHOOK_KEY:
        print(f"  [DRY RUN] Would notify: {movie} on {date} at {time}")
        return True
    
    webhook_url = f"https://maker.ifttt.com/trigger/{IFTTT_EVENT_NAME}/with/key/{IFTTT_WEBHOOK_KEY}"
    
    payload = {
        "value1": movie,
        "value2": f"{date} at {time}",
        "value3": url
    }
    
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"  ✅ Notified: {movie}")
            return True
        print(f"  ❌ Failed ({resp.status_code})")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    return False


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
    print(f"AMC Dolby Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Theater: AMC DINE-IN Thousand Oaks 14")
    print(f"{'='*50}\n")
    
    # Test IFTTT first
    print("Testing IFTTT connection...")
    test_ifttt()
    print()
    
    seen = load_seen()
    print(f"📋 {len(seen)} previously seen showtimes")
    
    print(f"🔍 Fetching Dolby showtimes (checking {DAYS_AHEAD} days)...\n")
    showtimes = get_dolby_showtimes(DAYS_AHEAD)
    
    print(f"\n📽️  Found {len(showtimes)} Dolby showtimes\n")
    
    if showtimes:
        for st in showtimes:
            print(f"   - {st['movie']} on {st['date']} at {st['time']}")
    
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
    
    save_seen(seen)
    print(f"\n💾 Cache updated ({len(seen)} total)")


if __name__ == "__main__":
    main()
