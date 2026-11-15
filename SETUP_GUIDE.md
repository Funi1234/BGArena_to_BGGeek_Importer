# Setup Guide - Getting Your Cookie Values

This guide walks you through extracting the necessary cookie values from your browser for both Board Game Arena and BoardGameGeek.

## Prerequisites

- You must be logged in to both Board Game Arena and BoardGameGeek
- Use Chrome, Firefox, Edge, or Brave (instructions are similar for all)

---

Your cookies grant access to your accounts. Keep `.env` private and never share it; on Unix, run `chmod 600 .env`. Git ignores `.env` and `.env.*`, but does not protect already tracked files or backups. The BGG connection check only tests a public page and does not verify authentication.

## Part 1: Board Game Arena (BGA) Cookies

### Step 1: Open BGA and DevTools

1. Go to [boardgamearena.com](https://boardgamearena.com) and **log in**
2. Navigate to your game stats page: `https://boardgamearena.com/gamestats`
3. Open Developer Tools:
   - **Windows/Linux**: Press `F12` or `Ctrl+Shift+I`
   - **Mac**: Press `Cmd+Option+I`

### Step 2: Capture Network Request

1. In DevTools, click the **Network** tab
2. Make sure recording is enabled (red circle button should be active)
3. **Refresh the page** (F5 or Cmd+R)
4. In the Network tab filter/search box, type: `getGames`
5. You should see a request to `getGames.html`

### Step 3: Copy as cURL

1. Right-click on the `getGames.html` request
2. Select **Copy** → **Copy as cURL** (or "Copy as cURL (bash)")
3. Paste it into a text editor

### Step 4: Extract Cookie Values

Your cURL command will look something like this (with lots of headers):

```bash
curl 'https://boardgamearena.com/gamestats/gamestats/getGames.html?player=12345678&...' \
  -H 'cookie: TournoiEnLigneid=abc123example; PHPSESSID=def456example; TournoiEnLignetk=ghi789example; ...' \
  ...
```

**Find the line starting with `-H 'cookie:'` or `-b '...'`**

Extract these specific values from the cookie string:

- `PHPSESSID=...` → copy the value after the equals sign
- `TournoiEnLigneid=...` → copy the value
- `TournoiEnLignetk=...` → copy the value
- `TournoiEnLigneidt=...` → copy the value
- `TournoiEnLignetkt=...` → copy the value

Also, from the URL in the cURL, find your player ID:
- `player=12345678` → this is your **BGA_PLAYER_ID**

### Step 5: Fill in .env (BGA Section)

```env
BGA_PLAYER_ID=12345678
BGA_USERNAME=YourBGAUsername
BGA_COOKIES={"PHPSESSID": "def456example", "TournoiEnLigneid": "abc123example", "TournoiEnLignetk": "ghi789example", "TournoiEnLigneidt": "jkl012example", "TournoiEnLignetkt": "mno345example"}
```

**Important:** 
- Use double quotes inside the JSON
- No spaces after colons in the JSON (it's fine but cleaner without)
- Make sure all cookie values are copied completely

---

## Part 2: BoardGameGeek (BGG) Cookies

### Step 1: Open BGG and DevTools

1. Go to [boardgamegeek.com](https://boardgamegeek.com) and **log in**
2. Navigate to any board game page (e.g., search for "Ark Nova")
3. Open Developer Tools (same as above: F12 or Cmd+Option+I)

### Step 2: Trigger a Play Log

1. In DevTools, click the **Network** tab
2. On the game page, click **"Log Play"** button
3. Fill in a test play (don't submit yet, or submit and we'll capture it)
4. In the Network tab, look for a request to `geekplay.php`
   - If you don't see it, try filtering by "geekplay"

### Step 3: Copy as cURL

1. Right-click on the `geekplay.php` request
2. Select **Copy** → **Copy as cURL**
3. Paste it into a text editor

### Step 4: Extract Cookie Values

Your cURL will look like:

```bash
curl 'https://boardgamegeek.com/geekplay.php' \
  -H 'cookie: bggusername=YourUsername; bggpassword=abc123def456example; SessionID=789xyz123u9876543example; _cfuvid=uvw456example; ...' \
  ...
```

**Find the cookie header and extract:**

- `bggusername=...` → copy the value (should be your username)
- `bggpassword=...` → copy the value (this is a hash, not your real password!)
- `SessionID=...` → copy the value (long alphanumeric string with a 'u' followed by numbers)
- `_cfuvid=...` → copy the value

**Also extract your User ID from the SessionID:**
- `SessionID=789xyz123u9876543example`
- Your user ID is the number after the 'u' → **9876543**

### Step 5: Fill in .env (BGG Section)

```env
BGG_USERNAME=YourBGGUsername
BGG_USER_ID=9876543
BGG_COOKIES={"bggusername": "YourBGGUsername", "bggpassword": "abc123def456example", "SessionID": "789xyz123u9876543example", "_cfuvid": "uvw456example"}
```

---

## Complete .env Example

Here's what your complete `.env` file should look like:

```env
# Board Game Arena Configuration
BGA_PLAYER_ID=12345678
BGA_USERNAME=YourBGAUsername
BGA_COOKIES={"PHPSESSID": "abc123example", "TournoiEnLigneid": "def456example", "TournoiEnLignetk": "ghi789example", "TournoiEnLigneidt": "jkl012example", "TournoiEnLignetkt": "mno345example"}

# BoardGameGeek Configuration
BGG_USERNAME=YourBGGUsername
BGG_USER_ID=9876543
BGG_COOKIES={"bggusername": "YourBGGUsername", "bggpassword": "pqr678example", "SessionID": "stu901exampleu9876543", "_cfuvid": "vwx234example"}
```

---

## Testing Your Configuration

Once you've filled in your `.env` file, test it:

```bash
# Test with a dry run
uv run main.py sync --dry-run --limit 3

# If that works, try a real sync
uv run main.py sync --limit 5
```

---

## Troubleshooting

### "Configuration errors: BGA_COOKIES not set or invalid JSON"

- Make sure the JSON is valid (use a JSON validator if needed)
- Check for missing commas or quotes
- Common mistake: using single quotes instead of double quotes

### "BGG connection failed"

- Your cookies might have expired - re-capture them
- Make sure you're logged in to BGG when capturing
- Try logging out and back in to BGG, then recapture cookies

### "Invalid date" or parsing errors

- Make sure you captured the cookies while logged in
- The cookies might be for a different user - verify the username matches

### Still having issues?

1. Try using an incognito/private window and logging in fresh
2. Clear your browser cookies and log in again
3. Make sure you're copying the ENTIRE cookie value (some are very long)

---

## Cookie Expiration

**Important:** Browser cookies expire! You may need to refresh them:

- BGA cookies: Typically last several weeks
- BGG cookies: Typically last several weeks

If you get authentication errors, just repeat this guide to get fresh cookies.

---

## Alternative: Using Browser Extensions (Advanced)

You can also use browser extensions like "EditThisCookie" or "Cookie-Editor" to view and copy cookies directly, but the cURL method above is more reliable and gives you all the values at once.
