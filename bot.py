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
        
        # 1. Isolate every single individual code block card element from the site layout source
        card_pattern = r'(font-mono text-xl font-bold tracking-wider">.*?<\/div>\s*<\/div>\s*<\/div>)'
        cards = re.findall(card_pattern, html, re.DOTALL)
        
        results = []
        for card in cards:
            # 2. Extract the actual raw gift code alphanumeric key string
            code_match = re.search(r'font-mono text-xl font-bold tracking-wider">(.*?)<\/p>', card)
            if not code_match:
                continue
            code = code_match.group(1).strip()
            
            # 3. Check for specific date configurations (MM/DD/YYYY) inside the captured block element
            expiry_match = re.search(r'Expires:\s*(\d{1,2}/\d{1,2}/\d{4})', card)
            expiry = expiry_match.group(1) if expiry_match else None
                
            results.append({"code": code, "expiry": expiry})
            
        print(f"Success! Scraped {len(results)} total active codes from the page layout.")
        return results
    except Exception as e:
        print(f"Scrape Error: {e}")
        return []

def run():
    if not WEBHOOK_URL:
        print("❌ Error: WEBHOOK_URL environment variable missing.")
        return

    # 1. Load Local State Sync Log
    msg_map = {}
    if os.path.exists(ID_MAP_FILE):
        try:
            with open(ID_MAP_FILE, "r") as f:
                msg_map = json.load(f)
        except:
            msg_map = {}

    # 2. Parse Valid Targets 
    current_data = get_code_data()
    active_codes_on_site = {item["code"]: item for item in current_data}
    
    session = requests.Session()

    # --- PART A: Processing Live / Added Web Entries ---
    for code in reversed(list(active_codes_on_site.keys())):
        item = active_codes_on_site[code]
        expiry = item["expiry"]
        
        # Build completely static string layouts without relative timer variables
        if expiry:
            content = f"<@&{ROLE_ID}> new code: `{code}` - expires {expiry}"
        else:
            content = f"<@&{ROLE_ID}> new code: `{code}`"

        if code not in msg_map:
            # Dispatch completely new individual text payload block
            try:
                res = session.post(f"{WEBHOOK_URL}?wait=true", json={"content": content})
                if res.status_code in [200, 201]:
                    msg_id = res.json().get("id")
                    msg_map[code] = {"id": msg_id, "status": "ACTIVE", "last_content": content}
                    print(f"✅ Dispatched unique entry post for: {code}")
            except Exception as e:
                print(f"❌ Post Transmission Error: {e}")
        
        else:
            # Sync context variations if prior memory cache mismatches actual live conditions
            msg_id = msg_map[code]["id"]
            last_content = msg_map[code].get("last_content", "")
            
            if msg_map[code].get("status") == "EXPIRED" or last_content != content:
                try:
                    res = session.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json={"content": content})
                    if res.status_code == 200:
                        msg_map[code]["status"] = "ACTIVE"
                        msg_map[code]["last_content"] = content
                        print(f"🔄 Corrected and verified data synchronization for code: {code}")
                except:
                    pass

    # --- PART B: Retracting Terminated Web Entries ---
    for code, data in msg_map.items():
        if code not in active_codes_on_site and data.get("status") == "ACTIVE":
            msg_id = data["id"]
            expired_content = f"code: `{code}` has **EXPIRED ❌**"
            
            try:
                res = session.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json={"content": expired_content})
                if res.status_code == 200:
                    msg_map[code]["status"] = "EXPIRED"
                    msg_map[code]["last_content"] = expired_content
                    print(f"💀 Marked as Expired: {code}")
            except Exception as e:
                print(f"❌ Retraction Edit Error: {e}")

    # 3. Save Context State Tracking Cache
    with open(ID_MAP_FILE, "w") as f:
        json.dump(msg_map, f, indent=4)
    print("Process execution runtime finalized.")

if __name__ == "__main__":
    run()
