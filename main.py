import os
import asyncio
import re
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
# আপনার দেওয়া ফায়ারবেস ইউআরএল
FB_URL = "https://otp-manager-511ec-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

sent_cache = set()
START_TIME = time.time()

def get_now():
    return datetime.now().strftime('%I:%M:%S %p')

def update_firebase(num, msg, date_str):
    """ফায়ারবেসে ডাটা আপডেট করার ফাংশন"""
    try:
        clean_num = re.sub(r'\D', '', num)
        url = f"{FB_URL}/sms_logs/{clean_num}.json"
        payload = {"number": num, "message": msg, "time": date_str, "paid": False}
        response = requests.put(url, json=payload, timeout=8)
        return response.status_code == 200
    except Exception:
        return False

def send_telegram(date_str, num, msg, is_system_msg=False, system_text=""):
    """টেলিগ্রামে মেসেজ পাঠানোর ফাংশন"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    if is_system_msg:
        payload = {"chat_id": CHAT_ID, "text": system_text, "parse_mode": "HTML"}
    else:
        masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num
        otp_match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
        otp = otp_match.group(1) if otp_match else ""

        text = f"🆕 <b>NEW SMS RECEIVED</b>\n\n" \
               f"🕒 <b>Time:</b> <code>{date_str}</code>\n" \
               f"📱 <b>Number:</b> <code>{masked}</code>\n"
        if otp: text += f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"
        text += f"\n💬 <b>Message:</b>\n<code>{msg}</code>"

        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[{"text": "🤖 FTC BOT", "url": "https://t.me/FTC_SUPER_SMS_BOT"}]]}
        }
        
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception: 
        return False

async def start_bot():
    print(f"[{get_now()}] 🚀 বট চালু হচ্ছে...")
    
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        async def login():
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                # আপনার অরিজিনাল লগিন স্ক্রিপ্ট এখানে থাকবে...
                login_success = await page.evaluate(f"""() => {{
                    try {{
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
                        return false;
                    }} catch (e) {{ return false; }}
                }}""")
                return login_success
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
                        d = (await cols[0].inner_text()).strip()
                        n = (await cols[2].inner_text()).strip()
                        s = (await cols[5].inner_text()).strip()
                        if d and len(re.sub(r'\D','',n)) >= 8:
                            valid_rows.append({"date": d, "num": n, "sms": s})
                
                if valid_rows:
                    latest = valid_rows[0]
                    uid = f"{latest['date']}|{latest['num']}|{latest['sms']}"

                    if is_first_scan:
                        # প্রথমবার চালুর কনফার্মেশন এবং প্রথম মেসেজ ফায়ার করা
                        tg_ok = send_telegram(latest['date'], latest['num'], latest['sms'])
                        fb_ok = update_firebase(latest['num'], latest['sms'], latest['date'])
                        
                        status_text = "ফায়ার করা হয়েছে এবং গ্রুপে পাঠানো হয়েছে" if (tg_ok and fb_ok) else "সমস্যা: ডাটাবেজ বা টেলিগ্রাম এরর"
                        print(f"[{get_now()}] 🟢 সর্বশেষ আসা মেসেজ: {latest['sms']}, নাম্বার: {latest['num']}, সময়: {latest['date']} - {status_text}।")
                        
                        # বাকিগুলো ক্যাশে ঢুকিয়ে দেওয়া যাতে ডুপ্লিকেট না হয়
                        for item in valid_rows:
                            sent_cache.add(f"{item['date']}|{item['num']}|{item['sms']}")
                        is_first_scan = False
                    
                    elif uid not in sent_cache:
                        # নতুন কোনো মেসেজ আসলে
                        tg_ok = send_telegram(latest['date'], latest['num'], latest['sms'])
                        fb_ok = update_firebase(latest['num'], latest['sms'], latest['date'])
                        
                        if tg_ok and fb_ok:
                            print(f"[{get_now()}] ✅ সর্বশেষ আসা মেসেজ এটি এবং নাম্বার {latest['num']} এবং সময় {latest['date']} - গ্রুপে পাঠানো হয়েছে এবং ডাটাবেজে আপডেট করা হয়েছে।")
                        else:
                            print(f"[{get_now()}] ❌ সর্বশেষ আসা মেসেজ এটি এবং নাম্বার {latest['num']} এবং সময় {latest['date']} - গ্রুপে আপডেট করা হয়নি, ডাটাবেজে আপডেট করা হয়নি। সমস্যা: কানেকশন এরর।")
                        
                        sent_cache.add(uid)
                    else:
                        # যদি নতুন মেসেজ না থাকে (আপনার চাহিদা অনুযায়ী লগ)
                        print(f"[{get_now()}] ⏳ সর্বশেষ আসা মেসেজ এটি এবং নাম্বার {latest['num']} এবং সময় {latest['date']} - এখনো গ্রুপে বা ডাটাবেজে নতুন কোনো আপডেট করা হয়নি।")

                if len(sent_cache) > 2000: sent_cache.clear()

            except Exception as e:
                print(f"[{get_now()}] ⚠️ সমস্যা: {str(e)}")
            
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start_bot())
