import os
import hmac
import hashlib
import base64
import logging
import uuid
from datetime import datetime

import requests
from flask import (
    Flask, render_template, request,
    abort, jsonify, make_response
)
from dotenv import load_dotenv
from auth import get_token

# ─── Configuration & Setup ─────────────────────────────────────────────────────
load_dotenv()
SECRET         = os.getenv("WEBHOOK_SECRET")
API_HOST       = os.getenv("API_HOST")         # e.g. "api.usw2.pure.cloud"
INTEGRATION_ID = os.getenv("INTEGRATION_ID")

app = Flask(__name__, static_folder="static", template_folder="templates")
logging.basicConfig(level=logging.INFO)

# ─── In‐Memory Transcript Buffer & Dedupe Set ───────────────────────────────────
transcript = []
processed_message_ids = set()


# ─── Helpers ────────────────────────────────────────────────────────────────────
def api_base_url() -> str:
    raw = API_HOST or ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = requests.utils.urlparse(raw)
    host = parsed.hostname or ""
    if not host.startswith("api."):
        host = f"api.{host}"
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    rebuilt = parsed._replace(netloc=netloc)
    return rebuilt.geturl().rstrip("/")


def verify_signature(raw: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    incoming = signature_header.split("sha256=")[1]
    expected = hmac.new(SECRET.encode(), raw, hashlib.sha256).digest()
    try:
        incoming_bytes = bytes.fromhex(incoming)
    except ValueError:
        try:
            incoming_bytes = base64.b64decode(incoming)
        except Exception:
            return False
    return hmac.compare_digest(expected, incoming_bytes)


# ─── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/messageFromGenesys", methods=["POST"])
def message_from_genesys():
    raw = request.get_data()
    sig = request.headers.get("X-Hub-Signature-256")
    if not sig or not verify_signature(raw, sig):
        abort(401, "Invalid signature")

    event   = request.get_json(force=True)
    payload = event.get("body", event)

    # 1) Extract text; if empty, ignore immediately
    text = payload.get("textBody") or payload.get("text")
    if not text:
        return ("", 200)

    # 2) Deduplicate only if an explicit messageId is provided
    explicit_id = payload.get("messageId") or payload.get("payload", {}).get("messageId")
    if explicit_id:
        if explicit_id in processed_message_ids:
            return ("", 200)
        processed_message_ids.add(explicit_id)

    # 3) Append the real agent message
    transcript.append({
        "sender":  "agent",
        "message": text,
        "purpose": "agent"
    })
    logging.info("Agent → %s%s",
                 text,
                 f"  (id: {explicit_id})" if explicit_id else "")
    return ("", 200)


@app.route("/messageToGenesys", methods=["POST"])
def message_to_genesys():
    data = request.get_json(force=True)
    msg  = data.get("message") or data.get("textBody")
    if not msg:
        return make_response("No message provided", 400)

    token = get_token()
    url   = f"{api_base_url()}/api/v2/conversations/messages/inbound/open"
    body  = {
        "id": data.get("id"),  # browser-generated session ID
        "channel": {
            "platform": "Open",
            "type":     "Private",
            "messageId": str(uuid.uuid4()),
            "to":       {"id": INTEGRATION_ID},
            "from":     {
                "nickname":  data.get("nickname"),
                "id":        data.get("id"),
                "idType":    data.get("idType"),
                "firstName": data.get("firstName"),
                "lastName":  data.get("lastName")
            },
            "time": datetime.utcnow().isoformat() + "Z"
        },
        "type":      "Text",
        "text":      msg,
        "direction": "Inbound"
    }
    resp = requests.post(
        url,
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json"
        }
    )
    if not resp.ok:
        logging.error("Inbound send failed %d: %s", resp.status_code, resp.text)
        return make_response("Upstream error", 502)

    transcript.append({
        "sender":  data.get("nickname"),
        "message": msg,
        "purpose": "customer"
    })
    logging.info("Customer → %s", msg)
    return ("", 200)


@app.route("/transcript", methods=["GET"])
def get_transcript():
    msgs = list(transcript)
    transcript.clear()
    return jsonify(msgs)


# ─── Run (with ngrok) ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from pyngrok import ngrok
    public_url = ngrok.connect(5000).public_url
    logging.info("ngrok tunnel: %s → http://127.0.0.1:5000", public_url)
    print(f" * Public URL: {public_url}")
    app.run(host="0.0.0.0", port=5000)
