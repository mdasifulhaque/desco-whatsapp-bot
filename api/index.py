import os
import requests
from http.server import BaseHTTPRequestHandler

# Fetch all configurations dynamically from Vercel Environment Variables
ACCOUNT_NUMBER = os.environ.get("DESCO_ACCOUNT")
PHONE_ID = os.environ.get("PHONE_NUMBER_ID")
TARGET_PHONE = os.environ.get("TARGET_MOBILE")
WA_TOKEN = os.environ.get("WHATSAPP_TOKEN")

def fetch_desco_profile():
    if not ACCOUNT_NUMBER:
        print("Missing DESCO_ACCOUNT environment variable.")
        return None
        
    url = f"https://prepaid.desco.org.bd/api/unified/customer/getBalance?accountNo={ACCOUNT_NUMBER}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://prepaid.desco.org.bd",
        "Referer": "https://prepaid.desco.org.bd/customer/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error querying DESCO database endpoints: {e}")
    return None

def push_whatsapp_notification(text_content):
    if not all([PHONE_ID, WA_TOKEN, TARGET_PHONE]):
        print("Missing WhatsApp connection credentials in environment variables.")
        return

    url = f"https://graph.facebook.com/v25.0/{PHONE_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TARGET_PHONE,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text_content
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=6)
        print(f"Meta Gateway Log: {response.json()}")
    except Exception as e:
        print(f"HTTP Meta delivery exception thrown: {e}")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        root_data = fetch_desco_profile()
        
        if root_data and "data" in root_data and root_data["data"] is not None:
            meter_data = root_data["data"]
            
            balance = meter_data.get("balance", "N/A")
            reading_date = meter_data.get("readingTime", "N/A")
            meter_id = meter_data.get("meterNo", "N/A")
            consumption = meter_data.get("currentMonthConsumption", "N/A")
            
            msg = (
                f"🔋 *DESCO Prepaid Update*\n\n"
                f"• Account No: `{ACCOUNT_NUMBER}`\n"
                f"• Meter Serial: `{meter_id}`\n"
                f"• *Remaining Balance:* *{balance} BDT*\n"
                f"• Current Month Usage: {consumption} kWh\n"
                f"• Reading Date: _{reading_date}_"
            )
        else:
            msg = f"⚠️ *DESCO Extraction Failure*\nCould not retrieve live metrics for account {ACCOUNT_NUMBER}."
            
        push_whatsapp_notification(msg)
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Automation cycle complete.")
        return
