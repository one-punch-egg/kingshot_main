import requests
import re
import os
import json

# --- CONFIGURATION ---
URL = "https://kingshotrewards.com/"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
ID_MAP_FILE = "message_ids.json" 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

def get_code_data():
    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text
        
        # Finds every code card block
        blocks = re.findall(r'relative bg-(.*?)</h5', html, re.DOTALL | re.IGNORECASE)
        
        code_results = []
        for block in blocks:
            status = "EXPIRED ❌" if "red-" in block else "ACTIVE ✅"
            code_match = re.search(r'<h5[^>]*>(.*)', block, re.IGNORECASE)
            if code_match:
                raw_text = code_match.group(1)
                clean_code = re.sub('<[^<]+?>', '', raw_text).strip()
                if 3 < len(clean_code) < 30:
                    code_results.append((clean_code, status))
        
        return code_results
    except Exception as e:
        print(f"Scrape Error: {e}")
        return []

def run():
    if not WEBHOOK_URL:
        print("Error: Webhook URL missing.")
        return

    msg_map = {}
    if os.path.exists(ID_MAP_FILE):
        try:
            with open(ID_MAP_FILE, "r") as f:
                msg_map = json.load(f)
        except:
            msg_map = {}

    # Get data and reverse it so newest is at the bottom of the chat
    current_data = get_code_data()
    current_data.reverse() 
    
    print(f"Checking {len(current_data)} codes (Cycle: Every 5 mins)...")

    for code, status in current_data:
        content = f"@everyone new code: `{code}` - **{status}**"

        # CASE 1: Brand New Code (Only post if Active on first discovery)
        if code not in msg_map:
            if status == "ACTIVE ✅":
                try:
                    res = requests.post(f"{WEBHOOK_URL}?wait=true", json={"content": content})
                    if res.status_code in [200, 201]:
                        msg_id = res.json().get("id")
                        msg_map[code] = {"id": msg_id, "status": status}
                        print(f"Successfully posted: {code}")
                except Exception as e:
                    print(f"Failed to post {code}: {e}")
            else:
                print(f"Found expired code {code}, skipping.")
        
        # CASE 2: Status flipped (Edit the existing message)
        elif msg_map[code]["status"] != status:
            msg_id = msg_map[code]["id"]
            edit_url = f"{WEBHOOK_URL}/messages/{msg_id}"
            try:
                requests.patch(edit_url, json={"content": content})
                msg_map[code]["status"] = status
                print(f"Successfully edited: {code}")
            except Exception as e:
                print(f"Failed to edit {code}: {e}")

    # Save mapping to JSON
    with open(ID_MAP_FILE, "w") as f:
        json.dump(msg_map, f, indent=4)

if __name__ == "__main__":
    run()
