import os
import requests
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Environment Configuration
# ---------------------------------------------------------------------------
ACCOUNT_NUMBER = os.environ.get("DESCO_ACCOUNT")
PHONE_ID       = os.environ.get("PHONE_NUMBER_ID")
TARGET_PHONE   = os.environ.get("TARGET_MOBILE")
WA_TOKEN       = os.environ.get("WHATSAPP_TOKEN")
CRON_SECRET    = os.environ.get("CRON_SECRET")

DESCO_TIMEOUT = 12
WA_TIMEOUT    = 8

# ---------------------------------------------------------------------------
# DESCO API Layer
# ---------------------------------------------------------------------------
def fetch_desco_profile() -> dict | None:
    if not ACCOUNT_NUMBER:
        print("[DESCO] DESCO_ACCOUNT env var is not set.")
        return None

    url = (
        "https://prepaid.desco.org.bd/api/unified/customer/getBalance"
        f"?accountNo={ACCOUNT_NUMBER}"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":  "application/json, text/plain, */*",
        "Origin":  "https://prepaid.desco.org.bd",
        "Referer": "https://prepaid.desco.org.bd/customer/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=DESCO_TIMEOUT, verify=False)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            print(f"[DESCO] Unexpected response shape: {type(payload)}")
            return None
        return payload
    except requests.exceptions.Timeout:
        print(f"[DESCO] Timed out after {DESCO_TIMEOUT}s.")
    except requests.exceptions.HTTPError as e:
        print(f"[DESCO] HTTP {e.response.status_code}: {e.response.text[:200]}")
    except requests.exceptions.ConnectionError as e:
        print(f"[DESCO] Connection error: {e}")
    except ValueError as e:
        print(f"[DESCO] JSON decode error: {e}")
    return None


# ---------------------------------------------------------------------------
# Message Formatters
# ---------------------------------------------------------------------------
def format_success_message(meter_data: dict) -> str:
    balance     = meter_data.get("balance",                 "—")
    meter_id    = meter_data.get("meterNo",                 "—")
    consumption = meter_data.get("currentMonthConsumption", "—")
    raw_date    = meter_data.get("readingTime",             "")
    reading_date = _humanise_date(raw_date) if raw_date else "—"

    balance_note = ""
    try:
        if float(balance) < 100:
            balance_note = "\n⚠️ _Low balance — consider recharging soon._"
    except (ValueError, TypeError):
        pass

    return (
        f"🔋 *DESCO Prepaid — Daily Update*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Account:* `{ACCOUNT_NUMBER}`\n"
        f"🔌 *Meter ID:* `{meter_id}`\n\n"
        f"💰 *Balance:* *{balance} BDT*{balance_note}\n"
        f"⚡ *This Month:* {consumption} kWh\n"
        f"🕐 *Reading:* _{reading_date}_\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def format_failure_message(reason: str = "") -> str:
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note = f"\n_Reason: {reason}_" if reason else ""
    return (
        f"⚠️ *DESCO Update Failed*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Could not retrieve data for account `{ACCOUNT_NUMBER}`.\n"
        f"Check API availability or account number.{note}\n"
        f"🕐 _{ts}_"
    )


def _humanise_date(raw: str) -> str:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            continue
    return raw


# ---------------------------------------------------------------------------
# WhatsApp Delivery Layer — MATCHED TO POSTMAN CONFIG
# ---------------------------------------------------------------------------
def _wa_post(payload: dict) -> tuple[int, dict]:
    """
    Shared HTTP transport matching working Postman collection configuration.
    Uses versionless endpoint to inherently adopt the App's native verified graph environment.
    """
    # Aligned version boundary route
    url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=WA_TIMEOUT)
        return resp.status_code, resp.json()
    except requests.exceptions.Timeout:
        print(f"[WhatsApp] Request timed out after {WA_TIMEOUT}s.")
    except requests.exceptions.ConnectionError as e:
        print(f"[WhatsApp] Connection error: {e}")
    except ValueError as e:
        print(f"[WhatsApp] JSON decode error on response: {e}")
    return 0, {}


def _send_hello_world() -> bool:
    payload = {
        "messaging_product": "whatsapp",
        "to":   TARGET_PHONE,
        "type": "template",
        "template": {
            "name":     "hello_world",
            "language": {"code": "en_US"},
        },
    }
    status, body = _wa_post(payload)
    if status == 200:
        msg_id = body.get("messages", [{}])[0].get("id", "unknown")
        print(f"[WhatsApp] Phase 1 (hello_world template) delivered. ID: {msg_id}")
        return True
    else:
        error = body.get("error", {})
        print(
            f"[WhatsApp] Phase 1 failed: {status} | "
            f"code={error.get('code')} | {error.get('message', str(body)[:200])}"
        )
        return False


def _send_free_text(text_content: str) -> bool:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                TARGET_PHONE,
        "type":              "text",
        "text": {
            "preview_url": False,
            "body":          text_content,
        },
    }
    status, body = _wa_post(payload)
    if status == 200:
        msg_id = body.get("messages", [{}])[0].get("id", "unknown")
        print(f"[WhatsApp] Phase 2 (report text) delivered. ID: {msg_id}")
        return True
    else:
        error = body.get("error", {})
        print(
            f"[WhatsApp] Phase 2 failed: {status} | "
            f"code={error.get('code')} | {error.get('message', str(body)[:200])}"
        )
        return False


def push_whatsapp_notification(text_content: str) -> bool:
    missing = [k for k, v in {
        "PHONE_NUMBER_ID": PHONE_ID,
        "TARGET_MOBILE":   TARGET_PHONE,
        "WHATSAPP_TOKEN":  WA_TOKEN,
    }.items() if not v]

    if missing:
        print(f"[WhatsApp] Missing env vars: {', '.join(missing)}. Delivery aborted.")
        return False

    phase1_ok = _send_hello_world()
    if not phase1_ok:
        print("[WhatsApp] Skipping Phase 2 due to Phase 1 failure.")
        return False

    return _send_free_text(text_content)


# ---------------------------------------------------------------------------
# Vercel Serverless Handler
# ---------------------------------------------------------------------------
class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if CRON_SECRET:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {CRON_SECRET}":
                self._respond(401, "Unauthorized.")
                return

        root_data  = fetch_desco_profile()
        meter_data = (root_data or {}).get("data")

        if meter_data and isinstance(meter_data, dict):
            msg     = format_success_message(meter_data)
            outcome = "success"
        else:
            api_reason = (root_data or {}).get("message", "")
            msg        = format_failure_message(api_reason)
            outcome    = "failure"

        push_whatsapp_notification(msg)
        print(f"[Handler] Pipeline complete. Outcome: {outcome}")
        self._respond(200, f"Pipeline complete: {outcome}")

    def _respond(self, status: int, body: str):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt, *args):
        pass
