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
conversations = {}

def get_products_from_sheet():
    try:
        url = f"https://docs.google.com/spreadsheets/d/1qxl48jTnCDp4gXjzPdvTcVgZg1864sQ7pwq_DLlkF6s/gviz/tq?tqx=out:json&sheet=Products"
        response = requests.get(url)
        text = response.text
        json_str = re.search(r'google\.visualization\.Query\.setResponse\((.*)\)', text, re.DOTALL)
        if not json_str:
            return []
        data = json.loads(json_str.group(1))
        rows = data['table']['rows']
        cols = [c['label'] for c in data['table']['cols']]
        products = []
        for row in rows:
            if row['c'][0] and row['c'][0]['v']:
                product = {}
                for i, col in enumerate(cols):
                    product[col] = row['c'][i]['v'] if row['c'][i] and row['c'][i]['v'] else ""
                products.append(product)
        return products
    except Exception as e:
        print(f"Sheet error: {e}")
        return []

def save_order(name, phone, product, color, quantity, address):
    try:
        data = {"name": name, "phone": phone, "product": product, "color": color, "quantity": quantity, "address": address}
        requests.post(APPS_SCRIPT_URL, json=data)
        return True
    except Exception as e:
        print(f"Order save error: {e}")
        return False

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        print(f"Telegram error: {e}")

def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    requests.post(url, params=params, json=data)

def send_image(recipient_id, image_url):
    try:
        url = "https://graph.facebook.com/v18.0/me/messages"
        params = {"access_token": PAGE_ACCESS_TOKEN}
        data = {
            "recipient": {"id": recipient_id},
            "message": {"attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}}}
        }
        requests.post(url, params=params, json=data)
    except Exception as e:
        print(f"Image send error: {e}")

def get_ai_reply(sender_id, user_message):
    try:
        if sender_id not in conversations:
            conversations[sender_id] = []

        conversations[sender_id].append({"role": "user", "content": user_message})

        if len(conversations[sender_id]) > 10:
            conversations[sender_id] = conversations[sender_id][-10:]

        products = get_products_from_sheet()
        product_text = "আমাদের Products:\n"
        for p in products:
            if str(p.get("Stock", "")).lower() == "yes":
                product_text += f"- {p.get('Product Name','')} ({p.get('Color','')}) : {p.get('Price','')} টাকা — {p.get('Description','')}\n"

        system_prompt = f"""আপনি OnePoint Easy Fashion এর customer service assistant।

{product_text}

আপনার কাজ:
1. Products সম্পর্কে জানানো
2. Customer ছবি দেখতে চাইলে [SEND_IMAGE:product_name:color] লিখুন
   যেমন: [SEND_IMAGE:face massager:red]
3. Order নেওয়া — ধাপে ধাপে জানুন: নাম, ফোন, product, রঙ, পিস, ঠিকানা
4. সব তথ্য পেলে [ORDER_COMPLETE] লিখুন তারপর JSON:
{{"name":"নাম","phone":"ফোন","product":"product","color":"রঙ","quantity":"পিস","address":"ঠিকানা"}}

বাংলায় কথা বলুন। বন্ধুত্বপূর্ণ থাকুন।"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system_prompt,
            messages=conversations[sender_id]
        )
        reply = response.content[0].text
        conversations[sender_id].append({"role": "assistant", "content": reply})

        # ছবি পাঠানো
        image_matches = re.findall(r'\[SEND_IMAGE:([^:]+):([^\]]+)\]', reply)
        for product_name, color in image_matches:
            for p in products:
                if p.get('Product Name','').lower() == product_name.strip().lower() and p.get('Color','').lower() == color.strip().lower():
                    if p.get('Image URL'):
                        send_image(sender_id, p['Image URL'])
            reply = reply.replace(f'[SEND_IMAGE:{product_name}:{color}]', '').strip()

        # Order complete
        if "[ORDER_COMPLETE]" in reply:
            json_match = re.search(r'\{[^}]+\}', reply)
            if json_match:
                order_data = json.loads(json_match.group())
                save_order(
                    order_data.get("name",""),
                    order_data.get("phone",""),
                    order_data.get("product",""),
                    order_data.get("color",""),
                    order_data.get("quantity",""),
                    order_data.get("address","")
                )
                telegram_msg = f"""🛍️ <b>নতুন Order!</b>
👤 নাম: {order_data.get('name','')}
📞 ফোন: {order_data.get('phone','')}
🛒 Product: {order_data.get('product','')} ({order_data.get('color','')})
🔢 পরিমাণ: {order_data.get('quantity','')}
📍 ঠিকানা: {order_data.get('address','')}
🕐 সময়: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                send_telegram(telegram_msg)
                conversations[sender_id] = []

            reply = reply.split("[ORDER_COMPLETE]")[0].strip()
            reply += "\n\n✅ আপনার অর্ডার নেওয়া হয়েছে! আমরা শীঘ্রই যোগাযোগ করব।"

        return reply
    except Exception as e:
        print(f"AI error: {e}")
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
                    ai_reply = get_ai_reply(sender_id, user_message)
                    send_message(sender_id, ai_reply)
    return jsonify({"status": "ok"}), 200

@app.route("/privacy")
def privacy():
    return app.send_static_file("privacy.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
