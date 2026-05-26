import os
import requests
from http.server import BaseHTTPRequestHandler

# Turn off SSL connection warning text logs caused by DESCO's cert issues
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Pull environment definitions from Vercel core securely
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
        # Bypassing strict SSL validation chains safely using verify=False
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error connecting to DESCO: {e}")
    return None

def push_whatsapp_template_alert(acc, meter, bal, usage, date):
    if not all([PHONE_ID, WA_TOKEN, TARGET_PHONE]):
        print("Missing WhatsApp connection credentials.")
        return

    url = f"https://graph.facebook.com/v25.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Restructured payload mapping custom utility data to Meta parameters
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TARGET_PHONE,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {
                "code": "en_US"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(acc)},
                        {"type": "text", "text": str(meter)},
                        {"type": "text", "text": f"{bal} BDT"},
                        {"type": "text", "text": f"{usage} kWh"},
                        {"type": "text", "text": str(date)}
                    ]
                }
            ]
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=6)
        print(f"Meta Gateway Log: {response.json()}")
    except Exception as e:
        print(f"Failed to transmit WhatsApp template: {e}")

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

        root_data = fetch_desco_profile()
        if root_data and "data" in root_data and root_data["data"] is not None:
            meter_data = root_data["data"]
            balance = meter_data.get("balance", "N/A")
            reading_date = meter_data.get("readingTime", "N/A")
            meter_id = meter_data.get("meterNo", "N/A")
            consumption = meter_data.get("currentMonthConsumption", "N/A")
            
            # Fire structural parameters straight out
            push_whatsapp_template_alert(ACCOUNT_NUMBER, meter_id, balance, consumption, reading_date)
        else:
            # Fallback values if the DESCO API experiences downtime
            push_whatsapp_template_alert(ACCOUNT_NUMBER, "ERR", "FETCH_FAILED", "ERR", "Check Online")
            
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Automation template processed.")
        return
