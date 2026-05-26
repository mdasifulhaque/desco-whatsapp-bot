import os
import requests
from http.server import BaseHTTPRequestHandler

# Turn off SSL connection warning text logs caused by DESCO's cert issues
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ACCOUNT_NUMBER = os.environ.get("DESCO_ACCOUNT")
PHONE_ID = os.environ.get("PHONE_NUMBER_ID")
TARGET_PHONE = os.environ.get("TARGET_MOBILE")
WA_TOKEN = os.environ.get("WHATSAPP_TOKEN")

def fetch_desco_profile():
    if not ACCOUNT_NUMBER:
        return None
    url = f"https://prepaid.desco.org.bd/api/unified/customer/getBalance?accountNo={ACCOUNT_NUMBER}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://prepaid.desco.org.bd",
        "Referer": "https://prepaid.desco.org.bd/customer/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error connecting to DESCO: {e}")
    return None

def open_sandbox_session():
    """Sends the clean, unparameterized hello_world template to open Meta's 24hr window."""
    url = f"https://graph.facebook.com/v25.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TARGET_PHONE,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"}
        }
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=6)
        print(f"Sandbox Session Opener Response: {res.json()}")
    except Exception as e:
        print(f"Failed to trigger template session opener: {e}")

def push_custom_text_alert(text_content):
    """Delivers the actual custom formatted text string containing your live data."""
    url = f"https://graph.facebook.com/v25.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TARGET_PHONE,
        "type": "text",
        "text": {"preview_url": False, "body": text_content}
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=6)
        print(f"Custom Balance Text Delivery Response: {res.json()}")
    except Exception as e:
        print(f"Failed to transmit custom text string: {e}")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth_header = self.headers.get('Authorization')
        cron_secret = os.environ.get('CRON_SECRET')
        
        if cron_secret and auth_header != f"Bearer {cron_secret}":
            self.send_response(401)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Unauthorized access attempt.")
            return

        # 1. Force open the sandbox conversation session block via template
        open_sandbox_session()

        # 2. Grab your live utility data parameters
        root_data = fetch_desco_profile()
        if root_data and "data" in root_data and root_data["data"] is not None:
            meter_data = root_data["data"]
            balance = meter_data.get("balance", "N/A")
            reading_date = meter_data.get("readingTime", "N/A")
            meter_id = meter_data.get("meterNo", "N/A")
            consumption = meter_data.get("currentMonthConsumption", "N/A")
            
            msg = (
                f"🔋 *DESCO Prepaid Update*\n\n"
                f"• *Account No:* `{ACCOUNT_NUMBER}`\n"
                f"• *Meter Serial:* `{meter_id}`\n"
                f"• *Remaining Balance:* *{balance} BDT*\n"
                f"• *Current Month Usage:* {consumption} kWh\n"
                f"• *Reading Date:* _{reading_date}_"
            )
        else:
            msg = f"⚠️ *DESCO Extraction Failure*\nCould not retrieve live metrics for account {ACCOUNT_NUMBER}."
            
        # 3. Fire the custom formatted message into the now open window session
        push_custom_text_alert(msg)
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Two-step sandbox transmission pipeline completed successfully.")
        return
