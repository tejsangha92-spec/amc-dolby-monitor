#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - GitHub Actions Version
Checks for new Dolby Cinema showtimes and sends IFTTT notifications.
"""

import requests
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Configuration from environment variables (set in GitHub repo settings)
IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
THEATER_SLUG = os.environ.get("THEATER_SLUG", "amc-dine-in-thousand-oaks-14")
IFTTT_EVENT_NAME = "new_dolby_showtime"
DAYS_AHEAD = 14
SEEN_FILE = Path("seen_dolby_showtimes.json")


def get_dolby_showtimes(theater_slug, days_ahead=14):
    """Fetch Dolby showtimes from AMC."""
    dolby_showtimes = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/html, */*",
    }
    
    for day_offset in range(days_ahead):
        date = datetime.now() + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")
        
        # Try AMC API endpoint
        url = f"https://www.amctheatres.com/api/v2/theatres/{theater_slug}/showtimes/{date_str}"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                showtimes = data.get("_embedded", {}).get("showtimes", [])
                
                for st in showtimes:
                    premium = st.get("premiumFormat", "").lower()
                    if "dolby" in premium:
                        dolby_showtimes.append({
                            "id": st.get("id"),
                            "movie": st.get("movieName", "Unknown"),
                            "date": date_str,
                            "time": st.get("showDateTimeLocal", ""),
                            "format": st.get("premiumFormat", "Dolby"),
                            "url": st.get("purchaseUrl", "")
                        })
        except Exception as e:
            print(f"  Error fetching {date_str}: {e}")
    
    # Fallback: try web scraping if API fails
    if not dolby_showtimes:
        dolby_showtimes = scrape_showtimes(theater_slug, days_ahead)
    
    return dolby_showtimes


def scrape_showtimes(theater_slug, days_ahead):
    """Fallback: scrape AMC website directly."""
    from bs4 import BeautifulSoup
    
    showtimes = []
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    for day_offset in range(days_ahead):
        date = datetime.now() + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")
        
        url = f"https://www.amctheatres.com/movie-theatres/los-angeles/{theater_slug}/showtimes/all/{date_str}/dolby-cinema-at-amc/all"
        
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200 and "dolby" in resp.text.lower():
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Look for structured data
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, list):
                            for item in data:
                                if item.get('@type') == 'ScreeningEvent':
                                    showtimes.append({
                                        'movie': item.get('workPresented', {}).get('name', 'Unknown'),
                                        'date': date_str,
                                        'time': item.get('startDate', ''),
                                        'format': 'Dolby Cinema',
                                        'url': item.get('url', '')
                                    })
                    except:
                        pass
        except Exception as e:
            print(f"  Scrape error {date_str}: {e}")
    
    return showtimes


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
        print(f"  ❌ Failed ({resp.status_code}): {movie}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    return False


def load_seen():
    """Load previously seen showtimes."""
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE) as f:
                data = json.load(f)
                # Clean entries older than 30 days
                cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                return {k: v for k, v in data.items() if v.get("date", "") >= cutoff}
        except:
            pass
    return {}


def save_seen(seen):
    """Save seen showtimes."""
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f, indent=2)


def main():
    print(f"\n{'='*50}")
    print(f"AMC Dolby Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Theater: {THEATER_SLUG}")
    print(f"{'='*50}\n")
    
    if not IFTTT_WEBHOOK_KEY:
        print("⚠️  IFTTT_WEBHOOK_KEY not set - running in dry-run mode\n")
    
    seen = load_seen()
    print(f"📋 {len(seen)} previously seen showtimes")
    
    print(f"🔍 Fetching Dolby showtimes...")
    showtimes = get_dolby_showtimes(THEATER_SLUG, DAYS_AHEAD)
    print(f"📽️  Found {len(showtimes)} Dolby showtimes\n")
    
    new_count = 0
    for st in showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            new_count += 1
            time_display = st['time'].split('T')[-1][:5] if 'T' in str(st['time']) else st['time']
            
            print(f"🎬 NEW: {st['movie']} - {st['date']} {time_display}")
            send_notification(st['movie'], time_display, st['date'], st.get('url', ''))
            
            seen[key] = {"date": st['date'], "added": datetime.now().isoformat()}
    
    if new_count == 0:
        print("✓ No new Dolby showtimes")
    else:
        print(f"\n🎉 {new_count} new showtimes found!")
    
    save_seen(seen)
    print(f"\n💾 Cache updated ({len(seen)} total)")


if __name__ == "__main__":
    main()
