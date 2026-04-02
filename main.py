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
FB_URL = "https://bot-pro-bd-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

sent_cache = set()
START_TIME = time.time()

def get_now():
    return datetime.now().strftime('%I:%M:%S %p')

# ===== ফায়ারবেজ আপডেট ফাংশন (Strict) =====
def update_firebase(num, msg, date_str):
    try:
        url = f"{FB_URL}/sms_logs/{num}.json"
        payload = {
            "number": num,
            "message": msg,
            "time": date_str,
            "paid": False
        }
        # ৫ সেকেন্ডের টাইমআউট, যাতে সার্ভার ডাউন থাকলে বট আটকে না যায়
        requests.put(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[{get_now()}] ⚠️ ফায়ারবেজ আপডেট এরর: {e}")

# ===== টেলিগ্রাম মেসেজ ফাংশন (Strict) =====
def send_telegram(date_str, num, msg, is_system_msg=False, system_text=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # যদি এটি সিস্টেম মেসেজ হয় (যেমন রিস্টার্ট মেসেজ)
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
        requests.post(url, json=payload, timeout=10)
        return True
    except Exception as e: 
        print(f"[{get_now()}] ❌ টেলিগ্রাম এরর: {e}")
        return False

# ===== মূল বট ফাংশন =====
async def start_bot():
    print(f"[{get_now()}] 🚀 FTC PRO (Bulletproof Mode) চালু হচ্ছে...")
    
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()

        async def login():
            print(f"[{get_now()}] 🔑 লগিন পেজে প্রবেশ করা হচ্ছে...")
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(2000)

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

                if login_success:
                    print(f"[{get_now()}] ✅ ক্রেডেনশিয়াল দেওয়া হয়েছে। লগিনের অপেক্ষা...")
                    await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"[{get_now()}] ❌ লগিন এরর: {str(e)}")

        # প্রথমবার লগিন
        await login()
        is_first_scan = True

        while True:
            # ৫ ঘণ্টা পর পর রিস্টার্ট (GitHub Actions limit)
            if time.time() - START_TIME > 18000: break
            
            try:
                # স্মার্ট সেশন রিকভারি
                if "login" in page.url:
                    print(f"[{get_now()}] ⚠️ সেশন নষ্ট হয়েছে! পুনরায় লগিন করা হচ্ছে...")
                    await login()
                    continue

                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                
                try:
                    await page.wait_for_selector("table tbody tr", timeout=10000)
                except:
                    print(f"[{get_now()}] ⚠️ টেবিল পাওয়া যায়নি, সেশন হয়তো এক্সপায়ার হয়েছে। লগিন ট্রাই করছি...")
                    await login()
                    continue
                
                rows = await page.query_selector_all("table tbody tr")
                valid_rows = []
                
                # কলাম 0 (Time), কলাম 2 (Number), কলাম 5 (Message)
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        date_str = (await cols[0].inner_text()).strip()
                        num = (await cols[2].inner_text()).strip()
                        sms = (await cols[5].inner_text()).strip()
                        
                        # Strict Filter: খালি না থাকলে এবং Loading লেখা না থাকলে
                        if date_str and num and sms and "Loading" not in date_str and "Loading" not in num:
                            valid_rows.append({"date": date_str, "num": num, "sms": sms})

                if valid_rows:
                    latest_msg = valid_rows[0]
                    found_new = False
                    
                    # যদি বটটি মাত্র স্টার্ট হয়ে থাকে (Silent Sync)
                    if is_first_scan:
                        print(f"[{get_now()}] 🔄 বট স্টার্ট হয়েছে! সর্বশেষ ডেটা সাইলেন্ট সিঙ্ক করা হচ্ছে...")
                        
                        for item in valid_rows[:20]: # প্রথম ২০টি মেসেজ মেমোরিতে ঢুকিয়ে নেবে
                            uid = f"{item['date']}|{item['num']}|{item['sms']}"
                            sent_cache.add(uid)
                        
                        # আপনাকে টেলিগ্রামে শুধু একটি নোটিফিকেশন পাঠাবে
                        sys_msg = f"🟢 <b>BOT ONLINE & SYNCED</b>\n\nবট সফলভাবে চালু হয়েছে এবং প্যানেল পাহারা দিচ্ছে।\n📌 <b>লেটেস্ট সিঙ্ক:</b> {latest_msg['date']}"
                        send_telegram("", "", "", is_system_msg=True, system_text=sys_msg)
                        
                        is_first_scan = False
                        found_new = True
                    
                    # সাধারণ স্ক্যানিং
                    else:
                        for item in valid_rows:
                            uid = f"{item['date']}|{item['num']}|{item['sms']}"
                            
                            # যদি ডেটা মেমোরিতে না থাকে, মানে একদম নতুন
                            if uid not in sent_cache:
                                if send_telegram(item['date'], item['num'], item['sms']):
                                    update_firebase(item['num'], item['sms'], item['date'])
                                    sent_cache.add(uid)
                                    found_new = True
                                    
                                    # ক্যাশ মেমোরি ক্লিয়ারেন্স (২০০০ আইটেম পর্যন্ত রাখবে)
                                    if len(sent_cache) > 2000: sent_cache.pop()
                    
                    # স্মার্ট লগিং
                    if found_new:
                        print(f"[{get_now()}] 📥 নতুন মেসেজ আপডেট করা হয়েছে!")
                        print(f"[{get_now()}] 📌 লেটেস্ট মেসেজ: {latest_msg['num']} | টাইম: {latest_msg['date']}")
                    else:
                        print(f"[{get_now()}] ⏳ স্ক্যান সম্পন্ন। নতুন ডেটা নেই। লেটেস্ট মেসেজ: {latest_msg['num']} | টাইম: {latest_msg['date']}")

                else:
                    print(f"[{get_now()}] ⚠️ টেবিলে কোনো ভ্যালিড ডেটা পাওয়া যায়নি।")

            except Exception as e:
                print(f"[{get_now()}] ⚠️ লুপ এরর: {str(e)}")
                try: await page.reload()
                except: pass
            
            # স্পিড ঠিক রাখতে ৪ সেকেন্ড পর পর চেক করবে
            await asyncio.sleep(4)

if __name__ == "__main__":
    asyncio.run(start_bot())
