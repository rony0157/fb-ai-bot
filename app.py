import os
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)

# ✅ এগুলো আপনার নিজের key দিয়ে পরিবর্তন করুন
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "আপনার_যেকোনো_একটা_কথা")  # যেকোনো word লিখুন
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")  # Facebook থেকে পাবেন
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # Anthropic থেকে পাবেন

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================
# Facebook Webhook Verify করা
# ============================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified!")
        return challenge, 200
    else:
        return "❌ Verification failed", 403


# ============================
# Message পাওয়া ও Reply করা
# ============================
@app.route("/webhook", methods=["POST"])
def handle_message():
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]

                # শুধু text message handle করব
                if "message" in event and "text" in event["message"]:
                    user_message = event["message"]["text"]
                    print(f"📩 Message received: {user_message}")

                    # AI দিয়ে reply তৈরি করুন
                    ai_reply = get_ai_reply(user_message)

                    # Facebook-এ reply পাঠান
                    send_message(sender_id, ai_reply)

    return jsonify({"status": "ok"}), 200


# ============================
# Claude AI দিয়ে Reply তৈরি
# ============================
def get_ai_reply(user_message):
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Fast & cheap model
            max_tokens=500,
            system="""আপনি একটি helpful customer service assistant। 
            বাংলা বা ইংরেজি যেভাবে প্রশ্ন করা হয় সেভাবে উত্তর দিন।
            উত্তর সংক্ষিপ্ত ও বন্ধুত্বপূর্ণ রাখুন।""",
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        return response.content[0].text
    except Exception as e:
        print(f"❌ AI error: {e}")
        return "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না। একটু পরে চেষ্টা করুন।"


# ============================
# Facebook-এ Message পাঠানো
# ============================
def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    response = requests.post(url, headers=headers, params=params, json=data)
    if response.status_code == 200:
        print("✅ Reply sent!")
    else:
        print(f"❌ Send failed: {response.text}")


# ============================
# Server চালু করা
# ============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
