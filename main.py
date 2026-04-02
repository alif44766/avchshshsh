import os
import asyncio
import re
import requests
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ===== GitHub Secrets থেকে কনফিগারেশন নেওয়া =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/login"

sent_cache = set()
START_TIME = time.time()

def get_now():
    return datetime.now().strftime('%H:%M:%S')

def send_telegram(num, msg):
    masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num
    otp_match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    otp = otp_match.group(1) if otp_match else ""

    text = f"🆕 <b>NEW SMS RECEIVED</b>\n\n" \
           f"📱 <b>Number:</b> <code>{masked}</code>\n"
    if otp:
        text += f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"
    text += f"\n💬 <b>Message:</b>\n<code>{msg}</code>"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": "🤖 FTC SUPER SMS BOT", "url": "https://t.me/FTC_SUPER_SMS_BOT"}]]}
    }
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except: return False

async def start_bot():
    print(f"[{get_now()}] 🚀 FTC PRO GitHub Actions-এ চালু হচ্ছে...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def login():
            print(f"[{get_now()}] 🔑 লগিন করার চেষ্টা করছি...")
            try:
                await page.goto(LOGIN_URL, timeout=60000)
                await page.fill('input[name="username"]', MY_USER)
                await page.fill('input[name="password"]', MY_PASS)
                content = await page.content()
                match = re.search(r'What is\s+(\d+)\s*\+\s*(\d+)', content)
                if match:
                    await page.fill('input[name="ans"]', str(int(match[1]) + int(match[2])))
                await page.click("button[type='submit']")
                await page.wait_for_timeout(5000)
                print(f"[{get_now()}] 🎉 লগিন সফল!")
            except Exception as e:
                print(f"[{get_now()}] ❌ লগিন এরর: {e}")

        await login()

        while True:
            # ৫ ঘণ্টা (১৮০০০ সেকেন্ড) হয়ে গেলে বট বন্ধ হবে যাতে নতুন শিডিউল শুরু হতে পারে
            if time.time() - START_TIME > 18000:
                print(f"[{get_now()}] 🔄 সেশন রিস্টার্টের জন্য বন্ধ হচ্ছে...")
                break

            try:
                if "login" in page.url: await login()
                await page.goto(TARGET_URL, timeout=60000)
                await page.wait_for_selector("table tbody tr", timeout=20000)
                
                rows = await page.query_selector_all("table tbody tr")
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        num = (await cols[2].inner_text()).strip()
                        sms = (await cols[5].inner_text()).strip()
                        uid = f"{num}|{sms}"
                        
                        if uid not in sent_cache:
                            if send_telegram(num, sms):
                                sent_cache.add(uid)
                                if len(sent_cache) > 500: sent_cache.pop()
                print(f"[{get_now()}] ⏳ স্ক্যানিং সম্পন্ন। নতুন কোনো ডেটা নেই।")
            except:
                await page.reload()
            
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start_bot())
