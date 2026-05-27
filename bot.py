import cloudscraper
import re
import os
import json
import requests

# --- CONFIGURATION ---
URL = "https://kingshot.net/gift-codes"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
ID_MAP_FILE = "message_ids.json"
ROLE_ID = "1479493265756524625" 

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
        
        # Isolate individual card elements so codes are captured even if they lack expiration HTML lines
        card_pattern = r'(font-mono text-xl font-bold tracking-wider">.*?<\/div>\s*<\/div>\s*<\/div>)'
        cards = re.findall(card_pattern, html, re.DOTALL)
        
        results = []
        for card in cards:
            code_match = re.search(r'font-mono text-xl font-bold tracking-wider">(.*?)<\/p>', card)
            if not code_match:
                continue
            code = code_match.group(1).strip()
            
            # Extract date explicitly ONLY if it is an actual date string format (MM/DD/YYYY)
            expiry_match = re.search(r'Expires:\s*(\d{1,2}/\d{1,2}/\d{4})<\/span>', card)
            expiry = expiry_match.group(1) if expiry_match else None
                
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
        
        # Construct content string safely based on real dates
        if expiry:
            content = f"<@&{ROLE_ID}> new code: `{code}` - expires {expiry}"
        else:
            content = f"<@&{ROLE_ID}> new code: `{code}`"

        if code not in msg_map:
            # POST NEW
            try:
                res = session.post(f"{WEBHOOK_URL}?wait=true", json={"content": content})
                if res.status_code in [200, 201]:
                    msg_id = res.json().get("id")
                    msg_map[code] = {"id": msg_id, "status": "ACTIVE", "last_content": content}
                    print(f"✅ Posted: {code}")
            except Exception as e:
                print(f"❌ Post Error: {e}")
        
        else:
            # Correct structural text on messages already active in the tracking cache
            msg_id = msg_map[code]["id"]
            last_content = msg_map[code].get("last_content", "")
            
            if msg_map[code].get("status") == "EXPIRED" or last_content != content:
                try:
                    res = session.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json={"content": content})
                    if res.status_code == 200:
                        msg_map[code]["status"] = "ACTIVE"
                        msg_map[code]["last_content"] = content
                        print(f"🔄 Corrected text data for active code: {code}")
                except:
                    pass

    # --- PART B: Handle Expired Codes (Gone from site) ---
    for code, data in msg_map.items():
        if code not in active_codes_on_site and data.get("status") == "ACTIVE":
            msg_id = data["id"]
            expired_content = f"code: `{code}` has **EXPIRED ❌**"
            
            try:
                res = session.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json={"content": expired_content})
                if res.status_code == 200:
                    msg_map[code]["status"] = "EXPIRED"
                    msg_map[code]["last_content"] = expired_content
                    print(f"💀 Marked Expired: {code}")
            except Exception as e:
                print(f"❌ Edit Error: {e}")

    # 3. Save Memory
    with open(ID_MAP_FILE, "w") as f:
        json.dump(msg_map, f, indent=4)
    print("Run complete.")

if __name__ == "__main__":
    run()
