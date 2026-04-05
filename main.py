import os
import sys
import asyncio
import re
import signal
import requests
import time
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ===== কনফিগারেশন =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/ints/login"
FB_URL = "https://bot-pro-bd-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

ADMIN_LINK = "https://t.me/Xero_Ridoy"
BOT_LINK = "https://t.me/FTC_SUPER_SMS_BOT"

# ক্যাশ মেমোরি: পুরনো মেসেজ মনে রাখার জন্য
seen_messages = set()

# ==========================================
# হেল্পার ফাংশন
# ==========================================

def extract_otp(msg):
    match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    return match.group(1) if match else "N/A"

def parse_dt(d_str):
    try:
        parts = d_str.split(' ')
        return parts[0][-5:], parts[1]
    except:
        return "??-??", "??:??:??"

# বটের স্ট্যাটাস (চালু/বন্ধ) গ্রুপে জানানোর ফাংশন
def send_status_alert(status_msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": status_msg, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# সার্ভার রিস্টার্ট হলে আগের সেশন বন্ধ করার সিগন্যাল
def handle_shutdown(signum, frame):
    print("🔴 সিগন্যাল পেয়ে বট বন্ধ হচ্ছে...")
    send_status_alert("🔴 <b><u>সার্ভার রিস্টার্ট:</u> আগের সেশনটি সফলভাবে বন্ধ করা হয়েছে!</b>\nনতুন সেশন এখনই চালু হবে।")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

# ==========================================
# ডাটাবেজ এবং টেলিগ্রাম সেন্ড লজিক
# ==========================================

# ফায়ারবেসে সম্পূর্ণ নতুন ইউনিক আইডি দিয়ে ডাটা সেভ করবে (Overwrite হবে না)
def add_to_firebase(num, msg, date_str, platform):
    try:
        url = f"{FB_URL}/sms_logs.json"
        payload = {"number": num, "platform": platform, "message": msg, "time": date_str, "paid": False}
        res = requests.post(url, json=payload, timeout=8)
        return res.status_code == 200
    except:
        return False

# টেলিগ্রাম গ্রুপে প্রিমিয়াম ডিজাইনে মেসেজ পাঠানো
def send_telegram(date_str, num, msg, otp, platform):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    masked = num[:4] + "XXXX" + num[-4:] if len(num) > 8 else num

    text = f"🌟 <b><u>ɴᴇᴡ sᴍs ᴀʀʀɪᴠᴇᴅ</u></b> 🌟\n" \
           f"━━━━━━━━━━━━━━━━━━━\n\n" \
           f"🌐 <b>Platform:</b> <code>{platform}</code>\n" \
           f"🕒 <b>Time:</b> <code>{date_str}</code>\n" \
           f"📱 <b>Number:</b> <code>{masked}</code>\n"
    
    if otp != "N/A":
        text += f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"
    
    text += f"━━━━━━━━━━━━━━━━━━━\n" \
           f"💬 <b>Message:</b>\n" \
           f"<blockquote>{msg}</blockquote>\n" \
           f"━━━━━━━━━━━━━━━━━━━"
    
    keyboard = []
    if otp != "N/A":
        keyboard.append([{"text": f"📋 Copy OTP: {otp}", "copy_text": {"text": otp}}])
    
    keyboard.append([
        {"text": "🤖 FTC BOT", "url": BOT_LINK},
        {"text": "👨‍💻 Admin", "url": ADMIN_LINK}
    ])

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": keyboard}
    }
        
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except: 
        return False

# ==========================================
# মূল বট লজিক (Scraping & Monitoring)
# ==========================================

async def start_bot():
    print("🚀 বট চালু হচ্ছে...")
    send_status_alert("🟢 <b><u>নতুন সেশন চালু হয়েছে:</u> FTC SMS BOT এখন নতুন মেসেজের জন্য প্রস্তুত!</b> 🚀")
    
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        async def login():
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                await page.evaluate(f"""() => {{
                    const myUser = "{MY_USER}"; const myPass = "{MY_PASS}";
                    let userField, passField, ansField;
                    document.querySelectorAll('input').forEach(inp => {{
                        let p = (inp.placeholder || "").toLowerCase();
                        if (inp.type === 'password') passField = inp;
                        else if (p.includes('user') || inp.type === 'text') {{ if (!userField && !p.includes('answer')) userField = inp; }}
                        if (p.includes('answer') || (inp.name || "").includes('ans')) ansField = inp;
                    }});
                    let match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                    let sum = match ? (parseInt(match[1]) + parseInt(match[2])) : "";
                    if (userField && passField && ansField && sum !== "") {{
                        userField.value = myUser; passField.value = myPass; ansField.value = sum;
                        userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        ansField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        for(let b of document.querySelectorAll('button, input[type="submit"]')) {{
                            if((b.innerText || b.value || "").toLowerCase().includes('login')) {{ b.click(); return true; }}
                        }}
                    }}
                }}""")
                return True
            except: return False

        await login()
        is_first_scan = True

        while True:
            try:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                
                if "login" in page.url:
                    await login()
                    continue
                
                valid_rows = []
                rows = await page.query_selector_all("table tbody tr")
                
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        d = (await cols[0].inner_text()).strip() # 0 = ডেট
                        n = (await cols[2].inner_text()).strip() # 2 = নাম্বার
                        p_form = (await cols[3].inner_text()).strip() # 3 = প্লাটফর্ম
                        s = (await cols[5].inner_text()).strip() # 5 = মেসেজ
                        
                        if d and len(re.sub(r'\D','',n)) >= 8:
                            valid_rows.append({"date": d, "num": n, "platform": p_form, "sms": s})
                
                if valid_rows:
                    if is_first_scan:
                        # প্রথম স্ক্যানে শুধু মেমোরিতে সেভ করবে, গ্রুপে স্প্যাম করবে না
                        for item in valid_rows:
                            fingerprint = f"{item['date']}|{item['num']}|{item['sms']}"
                            seen_messages.add(fingerprint)
                        is_first_scan = False
                        print("✅ First scan complete. Monitoring for NEW messages only...\n")
                    
                    else:
                        found_new = False
                        for item in reversed(valid_rows):
                            fingerprint = f"{item['date']}|{item['num']}|{item['sms']}"
                            d_short, t_short = parse_dt(item['date'])
                            otp = extract_otp(item['sms'])

                            # যদি মেসেজটি মেমোরিতে না থাকে (নতুন মেসেজ)
                            if fingerprint not in seen_messages:
                                tg = send_telegram(item['date'], item['num'], item['sms'], otp, item['platform'])
                                fb = add_to_firebase(item['num'], item['sms'], item['date'], item['platform'])
                                
                                seen_messages.add(fingerprint)
                                print(f"🆕 {d_short}◻️{t_short}◻️: [{item['platform']}] {item['num']}💬{item['sms']}\nGroup: {'✅' if tg else '❌'} DB: {'✅' if fb else '❌'}\n")
                                found_new = True
                        
                        if not found_new:
                            latest = valid_rows[0]
                            d_short, t_short = parse_dt(latest['date'])
                            print(f"🫆 No new message. Last: {d_short}◻️{t_short}◻️: {latest['num']}")

                # মেমোরি অপটিমাইজেশন (২৫০০ মেসেজের পর ক্লিয়ার হবে)
                if len(seen_messages) > 2500:
                    seen_messages.clear()
                    is_first_scan = True 

            except Exception as e:
                print(f"Error: {e}")
                pass
            
            await asyncio.sleep(4)

if __name__ == "__main__":
    asyncio.run(start_bot())
