import os
import json
import re
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic
from datetime import datetime

app = Flask(__name__, static_folder=".")

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

def save_order(name, phone, product, quantity, address):
    try:
        data = {"name": name, "phone": phone, "product": product, "quantity": quantity, "address": address}
        response = requests.post(APPS_SCRIPT_URL, json=data)
        print(f"✅ Order saved: {response.text}")
        return True
    except Exception as e:
        print(f"❌ Order save error: {e}")
        return False

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
        print("✅ Telegram sent!")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def get_ai_reply(user_message):
    try:
        system_prompt = """আপনি OnePoint Easy Fashion এর customer service assistant।

আমাদের Products:
- শাড়ি: 500 টাকা — সুন্দর কটন শাড়ি
- থ্রিপিস: 800 টাকা — এক্সক্লুসিভ থ্রিপিস
- কুর্তি: 350 টাকা — ট্রেন্ডি কুর্তি

আপনার কাজ:
1. Products সম্পর্কে জানানো
2. Order নেওয়া — এই তথ্য জানুন:
   - নাম
   - ফোন নম্বর
   - কোন product চান
   - কত পিস চান
   - ঠিকানা
3. সব তথ্য পেলে বলুন: "আপনার অর্ডার confirm করছি:" এবং সব তথ্য repeat করুন, তারপর লিখুন [ORDER_COMPLETE] এবং JSON:
{"name": "নাম", "phone": "ফোন", "product": "product", "quantity": "পরিমাণ", "address": "ঠিকানা"}

বাংলায় কথা বলুন। বন্ধুত্বপূর্ণ থাকুন।"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        reply = response.content[0].text
        print(f"🤖 AI reply: {reply[:100]}")

        if "[ORDER_COMPLETE]" in reply:
            json_match = re.search(r'\{[^}]+\}', reply)
            if json_match:
                order_data = json.loads(json_match.group())
                save_order(
                    order_data.get("name", ""),
                    order_data.get("phone", ""),
                    order_data.get("product", ""),
                    order_data.get("quantity", ""),
                    order_data.get("address", "")
                )
                telegram_msg = f"""🛍️ <b>নতুন Order!</b>
👤 নাম: {order_data.get('name', '')}
📞 ফোন: {order_data.get('phone', '')}
🛒 Product: {order_data.get('product', '')}
🔢 পরিমাণ: {order_data.get('quantity', '')}
📍 ঠিকানা: {order_data.get('address', '')}
🕐 সময়: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                send_telegram(telegram_msg)

            reply = reply.split("[ORDER_COMPLETE]")[0].strip()
            reply += "\n\n✅ আপনার অর্ডার নেওয়া হয়েছে! আমরা শীঘ্রই যোগাযোগ করব।"

        return reply
    except Exception as e:
        print(f"❌ AI error: {e}")
        return "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না।"

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def handle_message():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]
                if "message" in event and "text" in event["message"]:
                    user_message = event["message"]["text"]
                    print(f"📩 Message: {user_message}")
                    ai_reply = get_ai_reply(user_message)
                    send_message(sender_id, ai_reply)
    return jsonify({"status": "ok"}), 200

def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    requests.post(url, params=params, json=data)

@app.route("/privacy")
def privacy():
    return app.send_static_file("privacy.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
