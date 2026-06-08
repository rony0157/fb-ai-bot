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
SHEET_ID = "1qxl48jTnCDp4gXjzPdvTcVgZg1864sQ7pwq_DLlkF6s"

client = Anthropic(api_key=ANTHROPIC_API_KEY)
conversations = {}

def get_sheet_data(sheet_name):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:json&sheet={sheet_name}"
        response = requests.get(url)
        text = response.text
        json_str = re.search(r'google\.visualization\.Query\.setResponse\((.*)\)', text, re.DOTALL)
        if not json_str:
            return []
        data = json.loads(json_str.group(1))
        rows = data['table']['rows']
        cols = [c['label'] for c in data['table']['cols']]
        result = []
        for row in rows:
            if row['c'][0] and row['c'][0]['v']:
                item = {}
                for i, col in enumerate(cols):
                    item[col] = row['c'][i]['v'] if row['c'][i] and row['c'][i]['v'] else ""
                result.append(item)
        return result
    except Exception as e:
        print(f"Sheet error: {e}")
        return []

def get_settings():
    try:
        rows = get_sheet_data("Settings")
        settings = {}
        for row in rows:
            key = list(row.values())[0]
            value = list(row.values())[1] if len(row.values()) > 1 else ""
            settings[key] = value
        return settings
    except:
        return {}

def get_products():
    try:
        products = get_sheet_data("Products")
        return [p for p in products if str(p.get("Stock", "")).lower() == "yes"]
    except:
        return []

def save_order(order_data):
    try:
        requests.post(APPS_SCRIPT_URL, json=order_data)
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

        products = get_products()
        settings = get_settings()

        business_name = settings.get("business_name", "OnePoint")
        delivery_dhaka = settings.get("delivery_dhaka", 80)
        delivery_outside = settings.get("delivery_outside", 120)
        free_delivery = str(settings.get("free_delivery", "no")).lower()
        discount_percent = settings.get("discount_percent", 0)
        discount_message = settings.get("discount_message", "")

        product_text = "আমাদের Products:\n"
        for p in products:
            product_text += f"- {p.get('Product Name','')} ({p.get('Color','')}) : {p.get('Price','')} টাকা — {p.get('Description','')}\n"

        if free_delivery == "yes":
            delivery_text = "ডেলিভারি: সম্পূর্ণ বিনামূল্যে! 🎉"
        else:
            delivery_text = f"ডেলিভারি চার্জ: ঢাকার ভেতরে {delivery_dhaka} টাকা, ঢাকার বাইরে {delivery_outside} টাকা"

        discount_text = ""
        if discount_percent and float(str(discount_percent)) > 0:
            discount_text = f"🎊 বিশেষ অফার: {discount_percent}% ছাড়! {discount_message}"

        system_prompt = f"""আপনি {business_name} এর customer service assistant।

{product_text}

{delivery_text}
{discount_text}

আপনার কাজ:
1. Products সম্পর্কে জানানো ও ছবি দেখানো
2. Customer ছবি দেখতে চাইলে অবশ্যই এই exact format এ লিখুন: [SEND_IMAGE:face massager:green]
   product_name এবং color অবশ্যই lowercase এ লিখুন।
   উদাহরণ: customer "face massager red দেখাও" বললে লিখুন [SEND_IMAGE:face massager:red]
   এই tag ছাড়া ছবি পাঠানো সম্ভব না। - Customer যদি "কী আছে", "দেখাও", "product দেখি" বলে তাহলে সব product এর ছবি একে একে দেখাও
- Customer যদি recommendation চায় তাহলে একটা product suggest করে ছবি দেখাও
3. Order নেওয়া — ধাপে ধাপে জানুন: নাম, ফোন, product, রঙ, পিস, ঠিকানা
4. ঠিকানা পেলে delivery charge জানান
5. সব তথ্য পেলে [ORDER_COMPLETE] লিখুন তারপর JSON:
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
                save_order(order_data)
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
