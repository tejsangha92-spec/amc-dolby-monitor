#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - GitHub Actions Version
Checks for new Dolby Cinema showtimes and sends IFTTT notifications.
"""

import requests
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

# Configuration from environment variables
IFTTT_WEBHOOK_KEY = os.environ.get("IFTTT_WEBHOOK_KEY", "")
THEATER_SLUG = os.environ.get("THEATER_SLUG", "amc-dine-in-thousand-oaks-14")
IFTTT_EVENT_NAME = "new_dolby_showtime"
DAYS_AHEAD = 14
SEEN_FILE = Path("seen_dolby_showtimes.json")


def get_dolby_showtimes(theater_slug, days_ahead=14):
    """Fetch Dolby showtimes by scraping AMC website."""
    from bs4 import BeautifulSoup
    
    dolby_showtimes = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    for day_offset in range(days_ahead):
        date = datetime.now() + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")
        
        # Try the direct Dolby-filtered showtime page
        url = f"https://www.amctheatres.com/movie-theatres/los-angeles/{theater_slug}/showtimes/all/{date_str}/dolby-cinema-at-amc/all"
        
        try:
            print(f"  Checking {date_str}...")
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Method 1: Look for ShowtimesByTheatre data
                showtime_sections = soup.find_all(['div', 'section'], attrs={'data-movie-id': True})
                
                for section in showtime_sections:
                    movie_name = None
                    
                    # Try to find movie title
                    title_elem = section.find(['h2', 'h3', 'a'], class_=lambda c: c and ('title' in c.lower() or 'movie' in c.lower()) if c else False)
                    if title_elem:
                        movie_name = title_elem.get_text(strip=True)
                    
                    if not movie_name:
                        title_elem = section.find('a', href=lambda h: h and '/movies/' in h if h else False)
                        if title_elem:
                            movie_name = title_elem.get_text(strip=True)
                    
                    # Find showtimes
                    time_buttons = section.find_all(['a', 'button'], class_=lambda c: c and 'showtime' in c.lower() if c else False)
                    
                    for btn in time_buttons:
                        time_text = btn.get_text(strip=True)
                        if re.match(r'\d{1,2}:\d{2}', time_text):
                            dolby_showtimes.append({
                                'movie': movie_name or 'Unknown',
                                'date': date_str,
                                'time': time_text,
                                'format': 'Dolby Cinema',
                                'url': f"https://www.amctheatres.com{btn.get('href', '')}" if btn.get('href') else ''
                            })
                
                # Method 2: Look for JSON-LD structured data
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get('@type') == 'ScreeningEvent':
                                movie_name = item.get('workPresented', {}).get('name', 'Unknown')
                                start_date = item.get('startDate', '')
                                
                                # Check if Dolby
                                video_format = item.get('videoFormat', '')
                                location_name = item.get('location', {}).get('name', '')
                                
                                if 'dolby' in video_format.lower() or 'dolby' in location_name.lower():
                                    dolby_showtimes.append({
                                        'movie': movie_name,
                                        'date': date_str,
                                        'time': start_date,
                                        'format': 'Dolby Cinema',
                                        'url': item.get('url', '')
                                    })
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Method 3: Search page text for Dolby indicators
                if not dolby_showtimes:
                    page_text = response.text.lower()
                    if 'dolby' in page_text:
                        # Find all showtime links
                        all_links = soup.find_all('a', href=lambda h: h and '/showtimes/' in h if h else False)
                        
                        for link in all_links:
                            # Check parent elements for Dolby mention
                            parent = link.find_parent(['div', 'li', 'article', 'section'])
                            if parent:
                                parent_text = parent.get_text().lower()
                                if 'dolby' in parent_text:
                                    time_match = re.search(r'(\d{1,2}:\d{2}\s*[ap]m?)', link.get_text(), re.I)
                                    if time_match:
                                        # Try to find movie name
                                        movie_elem = parent.find(['h2', 'h3', 'a'], class_=lambda c: c and 'title' in str(c).lower() if c else False)
                                        movie_name = movie_elem.get_text(strip=True) if movie_elem else 'Unknown'
                                        
                                        dolby_showtimes.append({
                                            'movie': movie_name,
                                            'date': date_str,
                                            'time': time_match.group(1),
                                            'format': 'Dolby Cinema',
                                            'url': f"https://www.amctheatres.com{link.get('href', '')}"
                                        })
                        
        except requests.exceptions.RequestException as e:
            print(f"  Network error for {date_str}: {e}")
        except Exception as e:
            print(f"  Error for {date_str}: {e}")
    
    # Remove duplicates
    seen_keys = set()
    unique_showtimes = []
    for st in dolby_showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen_keys:
            seen_keys.add(key)
            unique_showtimes.append(st)
    
    return unique_showtimes


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
    
    print(f"🔍 Fetching Dolby showtimes (checking {DAYS_AHEAD} days)...\n")
    showtimes = get_dolby_showtimes(THEATER_SLUG, DAYS_AHEAD)
    
    print(f"\n📽️  Found {len(showtimes)} Dolby showtimes\n")
    
    if showtimes:
        print("All Dolby showtimes found:")
        for st in showtimes:
            print(f"   - {st['movie']} on {st['date']} at {st['time']}")
        print()
    
    new_count = 0
    for st in showtimes:
        key = f"{st['movie']}|{st['date']}|{st['time']}"
        if key not in seen:
            new_count += 1
            time_display = st['time']
            if 'T' in str(time_display):
                time_display = time_display.split('T')[-1][:5]
            
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
