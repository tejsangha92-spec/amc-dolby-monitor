# AMC Dolby Showtime Monitor (Cloud Version)

Get notified when new Dolby Cinema showtimes appear—runs entirely in the cloud via GitHub Actions. No local setup required.

## Setup (5 minutes)

### 1. Create GitHub Repository

1. Go to https://github.com/new
2. Name it something like `amc-dolby-monitor`
3. Make it **Private** (recommended) or Public
4. Click **Create repository**

### 2. Add the Files

Upload these two files to your new repo:

```
your-repo/
├── .github/
│   └── workflows/
│       └── check-dolby.yml
└── check_showtimes.py
```

**Option A: Upload via GitHub web interface**
- Click "Add file" → "Upload files"
- Drag both files (maintaining the folder structure for the workflow)

**Option B: Use git**
```bash
git clone https://github.com/YOUR_USERNAME/amc-dolby-monitor.git
cd amc-dolby-monitor
# Copy the files into place
git add .
git commit -m "Initial setup"
git push
```

### 3. Set Up IFTTT

1. Go to https://ifttt.com and create an account (free)

2. **Get your webhook key:**
   - Go to https://ifttt.com/maker_webhooks
   - Click "Connect" if not already connected
   - Click "Documentation" (top right)
   - Copy the key shown (long alphanumeric string)

3. **Create notification applet:**
   - Go to https://ifttt.com/create
   - Click "If This" → search "Webhooks" → "Receive a web request"
   - Event name: `new_dolby_showtime` (exact match required)
   - Click "Then That" → "Notifications" → "Send a notification from the IFTTT app"
   - Message: `🎬 {{Value1}} - {{Value2}}`
   - Click "Continue" → "Finish"

4. **Install IFTTT app** on your phone to receive push notifications

### 4. Configure GitHub Secrets & Variables

In your GitHub repo:

1. Go to **Settings** → **Secrets and variables** → **Actions**

2. Click **"New repository secret"**:
   - Name: `IFTTT_WEBHOOK_KEY`
   - Value: Your webhook key from step 3

3. Click **"Variables"** tab → **"New repository variable"**:
   - Name: `THEATER_SLUG`
   - Value: `amc-dine-in-thousand-oaks-14` (or your theater—see below)

### 5. Enable GitHub Actions

1. Go to **Actions** tab in your repo
2. Click **"I understand my workflows, go ahead and enable them"**
3. Click on "Check AMC Dolby Showtimes" workflow
4. Click **"Run workflow"** → **"Run workflow"** to test

You should receive a notification within a minute if there are any Dolby showtimes!

---

## Finding Your Theater Slug

1. Go to https://www.amctheatres.com/movie-theatres
2. Search for and click on your theater
3. Copy the last part of the URL

Examples:
| Theater | URL | Slug |
|---------|-----|------|
| AMC Thousand Oaks 14 | `.../amc-dine-in-thousand-oaks-14` | `amc-dine-in-thousand-oaks-14` |
| AMC Century City 15 | `.../amc-century-city-15` | `amc-century-city-15` |
| AMC Burbank 16 | `.../amc-burbank-16` | `amc-burbank-16` |

---

## How It Works

- **Schedule:** Runs every 6 hours automatically (kept well under GitHub's free 2,000 Actions minutes/month for private repos)
- **State:** Remembers which showtimes it already notified you about (via GitHub Actions cache)
- **Notifications:** Sends IFTTT webhook for each new Dolby showtime
- **Cost:** Free (within GitHub Actions free tier)

---

## Customization

**Change frequency:** Edit `.github/workflows/check-dolby.yml`:
```yaml
schedule:
  - cron: '0 */2 * * *'  # Every 2 hours
  - cron: '0 9,18 * * *' # 9am and 6pm UTC only
```

**Monitor multiple theaters:** Create multiple workflow files with different `THEATER_SLUG` variables.

**Change notification format:** Edit the `send_notification()` function in `check_showtimes.py`.

---

## Troubleshooting

**Workflow not running:**
- Check Actions tab for errors
- Ensure the workflow file is in `.github/workflows/`
- GitHub may delay scheduled runs by a few minutes

**No notifications:**
- Verify `IFTTT_WEBHOOK_KEY` secret is set correctly
- Check IFTTT app notifications are enabled
- Run workflow manually and check the logs

**"No Dolby showtimes found":**
- Verify your theater slug is correct
- Confirm the theater has Dolby Cinema
- Check workflow logs for API errors
