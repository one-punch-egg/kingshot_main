import cloudscraper
import re
import os
import json
import requests

# --- CONFIGURATION ---
URL = "https://kingshot.net/gift-codes"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
ID_MAP_FILE = "message_ids.json"
ROLE_ID = "1482141454607454308" 

def get_code_data():
    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        print(f"Fetching from {URL}...")
        response = scraper.get(URL, timeout=20)
        
        if response.status_code == 403:
            print("❌ Access Denied: Cloudflare block.")
            return []
            
        html = response.text
        # Matches the specific HTML structure provided
        pattern = r'font-mono text-xl font-bold tracking-wider">(.*?)<\/p>.*?Expires: (.*?)<\/span>'
        matches = re.findall(pattern, html, re.DOTALL)
        
        results = []
        for code_text, expiry_date in matches:
            code = code_text.strip()
            raw_expiry = expiry_date.strip()
            
            # CRITICAL FIX: Only treat it as an expiry date if it matches a date format (like MM/DD/YYYY)
            # If it says "7 months", text, or is empty, we set it to None so we don't post misinformation.
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', raw_expiry):
                expiry = f"expires {raw_expiry}"
            else:
                expiry = None 
                
            results.append({"code": code, "expiry": expiry})
            
        print(f"Success! Found {len(results)} active codes on site.")
        return results
    except Exception as e:
        print(f"Scrape Error: {e}")
        return []

def run():
    if not WEBHOOK_URL:
        print("❌ Error: WEBHOOK_URL missing.")
        return

    # 1. Load Memory
    msg_map = {}
    if os.path.exists(ID_MAP_FILE):
        try:
            with open(ID_MAP_FILE, "r") as f:
                msg_map = json.load(f)
        except:
            msg_map = {}

    # 2. Get Current Data
    current_data = get_code_data()
    active_codes_on_site = {item["code"]: item for item in current_data}
    
    session = requests.Session()

    # --- PART A: Handle New or Still Active Codes ---
    for code in reversed(list(active_codes_on_site.keys())):
        item = active_codes_on_site[code]
        expiry = item["expiry"]
        
        # Build message context dynamically based on whether a real date exists
        if expiry:
            content = f"<@&{ROLE_ID}> new code: `{code}` - {expiry}"
        else:
            content = f"<@&{ROLE_ID}> new code: `{code}`"

        if code not in msg_map:
            # POST NEW
            try:
                res = session.post(f"{WEBHOOK_URL}?wait=true", json={"content": content})
                if res.status_code in [200, 201]:
                    msg_id = res.json().get("id")
                    msg_map[code] = {"id": msg_id, "status": "ACTIVE"}
                    print(f"✅ Posted: {code}")
            except Exception as e:
                print(f"❌ Post Error: {e}")
        
        # Update existing message if it was previously marked Expired
        elif msg_map[code].get("status") == "EXPIRED":
            msg_id = msg_map[code]["id"]
            try:
                session.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json={"content": content})
                msg_map[code]["status"] = "ACTIVE"
                print(f"🔄 Reactivated: {code}")
            except: pass

    # --- PART B: Handle Expired Codes (Gone from site) ---
    for code, data in msg_map.items():
        if code not in active_codes_on_site and data.get("status") == "ACTIVE":
            msg_id = data["id"]
            
            # Formatting for EXPIRED status
            expired_content = (
                f"code: `{code}` has **EXPIRED ❌**"
            )
            
            try:
                res = session.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json={"content": expired_content})
                if res.status_code == 200:
                    msg_map[code]["status"] = "EXPIRED"
                    print(f"💀 Marked Expired: {code}")
            except Exception as e:
                print(f"❌ Edit Error: {e}")

    # 3. Save Memory
    with open(ID_MAP_FILE, "w") as f:
        json.dump(msg_map, f, indent=4)
    print("Run complete.")

if __name__ == "__main__":
    run()
