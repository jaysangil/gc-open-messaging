# app.py
import os
import hmac
import hashlib
import base64
import logging
import urllib.parse
from flask import Flask, request, abort, make_response
from dotenv import load_dotenv
from auth import get_token
import requests

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Configuration from environment
SECRET         = os.getenv("WEBHOOK_SECRET")
API_HOST       = os.getenv("API_HOST")         # e.g. "api.mypurecloud.com"
INTEGRATION_ID = os.getenv("INTEGRATION_ID")

logging.basicConfig(level=logging.INFO)

def api_base_url() -> str:
    """
    Build a valid base URL for the Genesys Cloud API.
    Ensures the host is prefixed with "api." and has https://
    """
    raw = API_HOST or ""
    # ensure scheme
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urllib.parse.urlparse(raw)
    hostname = parsed.hostname or ""
    # add "api." if missing
    if not hostname.startswith("api."):
        hostname = f"api.{hostname}"
    # reconstruct netloc (incl. port if any)
    netloc = hostname + (f":{parsed.port}" if parsed.port else "")
    rebuilt = parsed._replace(netloc=netloc)
    return urllib.parse.urlunparse(rebuilt).rstrip("/")

def verify_signature(payload: bytes, signature_header: str) -> bool:
    """
    Accepts both hex-encoded and Base64-encoded sha256 HMACs.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    incoming = signature_header.split("sha256=")[1]

    # Compute raw HMAC bytes
    expected_bytes = hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()

    # Decode incoming signature
    try:
        # try hex first
        incoming_bytes = bytes.fromhex(incoming)
    except ValueError:
        # fallback to Base64
        try:
            incoming_bytes = base64.b64decode(incoming)
        except Exception:
            return False

    return hmac.compare_digest(expected_bytes, incoming_bytes)

@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Hub-Signature-256")

    # Log computed signature for debugging
    try:
        computed_hex = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        logging.info("Incoming Signature: %s", sig)
        logging.info("Computed Signature (hex): sha256=%s", computed_hex)
    except Exception:
        pass

    if not sig:
        abort(400, "Missing signature header")
    if not verify_signature(raw, sig):
        abort(401, "Invalid signature")

    event = request.get_json(force=True, silent=True)
    logging.info("Received webhook event: %s", event)

    # Normalize payload (nested under "body" or flat)
    payload = event.get("body") if isinstance(event, dict) and "body" in event else event

    # Receipt
    if payload.get("type") == "Receipt" or ("status" in payload and "messageId" in payload):
        return handle_receipt(payload)

    # Structured interactive
    if payload.get("payload", {}).get("interactive"):
        return handle_interactive(payload)

    # Nested Message
    if payload.get("type") == "Message" and "text" in payload:
        return handle_text(payload)

    # Flat agentless payload
    if "textBody" in payload and "fromAddress" in payload:
        normalized = {
            "conversationId":   payload.get("conversationId", ""),
            "messageId":        payload.get("messageId", ""),
            "fromAddress":      payload["fromAddress"],
            "text":             payload["textBody"],
            "customAttributes": payload.get("customAttributes", {})
        }
        return handle_text(normalized)

    logging.warning("Unhandled event structure: %s", payload)
    return ("", 204)

def handle_receipt(body: dict):
    receipt_id     = body.get("messageId")
    receipt_status = body.get("status")
    logging.info("Receipt: messageId=%s status=%s", receipt_id, receipt_status)
    return ("", 200)

def handle_interactive(body: dict):
    from_addr   = body.get("fromAddress")
    interactive = body["payload"]["interactive"]
    itype       = interactive.get("type")
    button      = interactive.get("button")
    date_picker = interactive.get("datePicker")

    if itype == "button" and button:
        text = f"You pressed '{button['text']}' (payload: {button['payload']})"
        return send_reply(from_addr, text)

    if itype == "datePicker" and date_picker:
        text = f"You chose {date_picker['value']}"
        return send_reply(from_addr, text)

    return send_reply(from_addr, "Unsupported structured response")

def handle_text(body: dict):
    incoming  = body.get("text")
    from_addr = body.get("fromAddress")
    logging.info("Text msg from %s: %s", from_addr, incoming)

    if incoming and incoming.lower() == "options":
        buttons = [
            {"type": "quickReply", "text": "First option",  "payload": "first_option"},
            {"type": "quickReply", "text": "Second option", "payload": "second_option"}
        ]
        return send_structured_reply(from_addr, "Please choose an option:", buttons)

    return send_reply(from_addr, f"Echo: {incoming}")

def send_reply(to_addr: str, text: str):
    url = f"{api_base_url()}/api/v2/conversations/messages/agentless"
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }
    payload = {
        "fromAddress":                   INTEGRATION_ID,
        "toAddress":                     to_addr,
        "toAddressMessengerType":        "open",
        "textBody":                      text,
        "messagingTemplate":             None,
        "useExistingActiveConversation": True
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if not resp.ok:
            logging.error("Genesys reply failed [%d]: %s", resp.status_code, resp.text)
            return make_response("Upstream messaging error", 502)
        logging.info("Sent text reply to %s", to_addr)
        return ("", 200)

    except requests.exceptions.RequestException as e:
        logging.error("Error sending reply: %s", e)
        return make_response("Error communicating with Genesys Cloud", 502)

def send_structured_reply(to_addr: str, text: str, buttons: list):
    url = f"{api_base_url()}/api/v2/conversations/messages/agentless"
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }
    payload = {
        "fromAddress":                   INTEGRATION_ID,
        "toAddress":                     to_addr,
        "toAddressMessengerType":        "open",
        "structuredBody": {
            "text":    text,
            "type":    "quickReply",
            "buttons": buttons
        },
        "messagingTemplate":             None,
        "useExistingActiveConversation": True
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if not resp.ok:
            logging.error("Genesys structured reply failed [%d]: %s", resp.status_code, resp.text)
            return make_response("Upstream messaging error", 502)
        logging.info("Sent structured reply to %s", to_addr)
        return ("", 200)

    except requests.exceptions.RequestException as e:
        logging.error("Error sending structured reply: %s", e)
        return make_response("Error communicating with Genesys Cloud", 502)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
