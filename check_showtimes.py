#!/usr/bin/env python3
"""
AMC Dolby Showtime Monitor - Improved Fandango scraping with better Dolby detection
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
# Fandango theater ID for AMC Thousand Oaks 14
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
            
            # Fandango URL
            url = f"https://www.fandango.com/amc-dine-in-thousand-oaks-14-{FANDANGO_THEATER_ID}/theater-page?date={date_str}"
            
            print(f"  Checking {date_str}...")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)  # Wait for dynamic content
                
                # Get the full HTML to search for Dolby
                html_content = page.content()
                full_text = page.inner_text('body')
                
                # Debug output on first day
                if day_offset == 0:
                    print(f"\n--- PAGE TEXT (first 4000 chars) ---")
                    print(full_text[:4000])
                    print(f"--- END ---\n")
                    print(f"Total text length: {len(full_text)} chars")
                    
                    # Check if Dolby appears anywhere
                    dolby_count = full_text.lower().count('dolby')
                    print(f"'Dolby' appears {dolby_count} times in page text")
                    
                    if dolby_count > 0:
                        # Find context around Dolby mentions
                        for match in re.finditer(r'.{0,100}dolby.{0,100}', full_text.lower()):
                            print(f"  Context: ...{match.group()}...")
                
                # Method 1: Look for Dolby Cinema sections in the HTML
                # Fandango often has format icons/labels
                if 'dolby' in html_content.lower():
                    # Try to find movie sections that contain Dolby
                    movie_sections = page.locator('[class*="movie"], [class*="showtime"], [data-movie]').all()
                    
                    for section in movie_sections:
                        try:
                            section_html = section.inner_html()
                            section_text = section.inner_text()
                            
                            if 'dolby' in section_html.lower() or 'dolby' in section_text.lower():
                                # Found a Dolby section - extract movie name and times
                                movie_match = re.search(r'([A-Za-z0-9\s:,\'-]+)\s*\((\d{4})\)', section_text)
                                if movie_match:
                                    movie_name = f"{movie_match.group(1).strip()} ({movie_match.group(2)})"
                                    
                                    # Find times (format: 6:00p, 9:00pm, 6:00 PM, etc)
                                    times = re.findall(r'(\d{1,2}:\d{2}\s*[ap]\.?m?\.?)', section_text.lower())
                                    
                                    for t in times:
                                        # Normalize time format
                                        t_clean = t.replace(' ', '').replace('.', '').rstrip('m')
                                        if not t_clean.endswith('m'):
                                            t_clean = t_clean  # Already like "6:00p"
                                        
                                        showtime = {
                                            'movie': movie_name,
                                            'date': date_str,
                                            'time': t_clean,
                                        }
                                        dolby_showtimes.append(showtime)
                                        print(f"    🎬 {movie_name} at {t_clean}")
                        except Exception as e:
                            pass
                
                # Method 2: Parse text more aggressively
                # Look for pattern: Movie Name (Year) ... Dolby ... times
                lines = full_text.split('\n')
                current_movie = None
                in_dolby_section = False
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Movie titles have year in parens
                    movie_match = re.search(r'^(.+?)\s*\((\d{4})\)$', line)
                    if movie_match:
                        current_movie = line
                        in_dolby_section = False
                        continue
                    
                    # Check if this line or nearby lines mention Dolby
                    if 'dolby' in line.lower():
                        in_dolby_section = True
                        continue
                    
                    # If we're in a Dolby section and have a movie, look for times
                    if current_movie and in_dolby_section:
                        times = re.findall(r'(\d{1,2}:\d{2}\s*[ap]\.?m?\.?)', line.lower())
                        for t in times:
                            t_clean = t.replace(' ', '').replace('.', '').rstrip('m')
                            showtime = {
                                'movie': current_movie,
                                'date': date_str,
                                'time': t_clean,
                            }
                            if showtime not in dolby_showtimes:
                                dolby_showtimes.append(showtime)
                                print(f"    🎬 {current_movie} at {t_clean}")
                        
                        # Reset after finding times
                        if times:
                            in_dolby_section = False
                
                # Method 3: Look for Dolby format buttons/links
                try:
                    dolby_elements = page.locator('text=/dolby/i').all()
                    for elem in dolby_elements:
                        try:
                            # Get parent container
                            parent = elem.locator('xpath=ancestor::*[contains(@class, "showtime") or contains(@class, "movie")]').first
                            parent_text = parent.inner_text()
                            
                            movie_match = re.search(r'([A-Za-z0-9\s:,\'-]+)\s*\((\d{4})\)', parent_text)
                            if movie_match:
                                movie_name = f"{movie_match.group(1).strip()} ({movie_match.group(2)})"
                                times = re.findall(r'(\d{1,2}:\d{2}\s*[ap]\.?m?\.?)', parent_text.lower())
                                
                                for t in times:
                                    t_clean = t.replace(' ', '').replace('.', '').rstrip('m')
                                    showtime = {
                                        'movie': movie_name,
                                        'date': date_str,
                                        'time': t_clean,
                                    }
                                    if showtime not in dolby_showtimes:
                                        dolby_showtimes.append(showtime)
                                        print(f"    🎬 {movie_name} at {t_clean}")
                        except:
                            pass
                except:
                    pass
                
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
