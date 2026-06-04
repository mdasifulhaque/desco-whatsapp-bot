import os
import json
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

DESCO_TIMEOUT = 12   # seconds — DESCO API is occasionally sluggish
WA_TIMEOUT    = 8    # seconds

# ---------------------------------------------------------------------------
# DESCO API Layer
# ---------------------------------------------------------------------------
def fetch_desco_profile() -> dict | None:
    """
    Fetches prepaid meter data from DESCO's unified customer API.
    Returns the parsed JSON dict on success, None on any failure.
    verify=False is intentional — DESCO has persistent TLS chain issues.
    """
    if not ACCOUNT_NUMBER:
        print("[DESCO] DESCO_ACCOUNT env var is not set. Aborting fetch.")
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
        "Accept":   "application/json, text/plain, */*",
        "Origin":   "https://prepaid.desco.org.bd",
        "Referer":  "https://prepaid.desco.org.bd/customer/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=DESCO_TIMEOUT, verify=False)
        resp.raise_for_status()                     # surface 4xx / 5xx clearly
        payload = resp.json()
        if not isinstance(payload, dict):
            print(f"[DESCO] Unexpected response shape: {type(payload)}")
            return None
        return payload
    except requests.exceptions.Timeout:
        print(f"[DESCO] Request timed out after {DESCO_TIMEOUT}s.")
    except requests.exceptions.HTTPError as e:
        print(f"[DESCO] HTTP error: {e.response.status_code} — {e.response.text[:200]}")
    except requests.exceptions.ConnectionError as e:
        print(f"[DESCO] Connection error: {e}")
    except ValueError as e:
        print(f"[DESCO] JSON decode failure: {e}")
    return None


# ---------------------------------------------------------------------------
# Message Formatter
# ---------------------------------------------------------------------------
def format_success_message(meter_data: dict) -> str:
    balance     = meter_data.get("balance",                   "—")
    meter_id    = meter_data.get("meterNo",                   "—")
    consumption = meter_data.get("currentMonthConsumption",   "—")
    raw_date    = meter_data.get("readingTime",               "")

    # Attempt to humanise the reading date if it's a parseable ISO string
    reading_date = _humanise_date(raw_date) if raw_date else "—"

    # Balance threshold hint (handy when balance is low)
    balance_note = ""
    try:
        if float(balance) < 100:
            balance_note = "\n⚠️ _Low balance — consider recharging soon._"
    except (ValueError, TypeError):
        pass

    return (
        f"🔋 *DESCO Prepaid — Daily Update*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Account:*  `{ACCOUNT_NUMBER}`\n"
        f"🔌 *Meter ID:* `{meter_id}`\n\n"
        f"💰 *Balance:*  *{balance} BDT*{balance_note}\n"
        f"⚡ *This Month:* {consumption} kWh\n"
        f"🕐 *Reading:*  _{reading_date}_\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def format_failure_message(reason: str = "") -> str:
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note = f"\n_Reason: {reason}_" if reason else ""
    return (
        f"⚠️ *DESCO Update Failed*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Could not retrieve data for account `{ACCOUNT_NUMBER}`.\n"
        f"Check API availability or account number.{note}\n"
        f"🕐 _{ts}_"
    )


def _humanise_date(raw: str) -> str:
    """
    Best-effort ISO 8601 → readable string.
    Falls back to returning the raw value unchanged.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            continue
    return raw   # unrecognised format — return as-is


# ---------------------------------------------------------------------------
# WhatsApp Delivery Layer
# ---------------------------------------------------------------------------
def push_whatsapp_notification(text_content: str) -> bool:
    """
    Posts a plain-text message to the target WhatsApp number via Meta Cloud API.
    Returns True on a successful 200 response, False otherwise.
    """
    missing = [k for k, v in {
        "PHONE_NUMBER_ID": PHONE_ID,
        "TARGET_MOBILE":   TARGET_PHONE,
        "WHATSAPP_TOKEN":  WA_TOKEN,
    }.items() if not v]

    if missing:
        print(f"[WhatsApp] Missing env vars: {', '.join(missing)}. Delivery aborted.")
        return False

    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                TARGET_PHONE,
        "type":              "text",
        "text": {
            "preview_url": False,
            "body":        text_content,
        },
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=WA_TIMEOUT)
        resp_json = resp.json()

        if resp.status_code == 200:
            msg_id = resp_json.get("messages", [{}])[0].get("id", "unknown")
            print(f"[WhatsApp] Delivered. Message ID: {msg_id}")
            return True
        else:
            # Meta returns structured error objects — log them clearly
            error = resp_json.get("error", {})
            print(
                f"[WhatsApp] Delivery failed: {resp.status_code} | "
                f"code={error.get('code')} | {error.get('message', resp.text[:200])}"
            )
            return False

    except requests.exceptions.Timeout:
        print(f"[WhatsApp] Request timed out after {WA_TIMEOUT}s.")
    except requests.exceptions.ConnectionError as e:
        print(f"[WhatsApp] Connection error: {e}")
    except ValueError as e:
        print(f"[WhatsApp] JSON decode error on response: {e}")
    return False


# ---------------------------------------------------------------------------
# Vercel Serverless Handler
# ---------------------------------------------------------------------------
class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # ── Auth guard ────────────────────────────────────────────────────
        if CRON_SECRET:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {CRON_SECRET}":
                self._respond(401, "Unauthorized.")
                return

        # ── Pipeline ──────────────────────────────────────────────────────
        root_data = fetch_desco_profile()

        meter_data = (root_data or {}).get("data")
        if meter_data and isinstance(meter_data, dict):
            msg = format_success_message(meter_data)
            outcome = "success"
        else:
            # Surface any top-level error message the API may have returned
            api_reason = (root_data or {}).get("message", "")
            msg = format_failure_message(api_reason)
            outcome = "failure"

        push_whatsapp_notification(msg)

        print(f"[Handler] Pipeline complete. Outcome: {outcome}")
        self._respond(200, f"Pipeline complete: {outcome}")

    def _respond(self, status: int, body: str):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # Silence the default BaseHTTPRequestHandler request log line
    # (Vercel already captures stdout; double-logging is noisy)
    def log_message(self, fmt, *args):
        pass
