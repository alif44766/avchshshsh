import os
import asyncio
import re
import requests
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ===== কনফিগারেশন =====
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

# ===== টেলিগ্রামে মেসেজ পাঠানোর ফাংশন =====
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
    except Exception as e: 
        print(f"[{get_now()}] ❌ টেলিগ্রাম এরর: {e}")
        return False

# ===== মূল বট ফাংশন =====
async def start_bot():
    print(f"[{get_now()}] 🚀 FTC PRO V23 (Advanced Mode) চালু হচ্ছে...")
    async with async_playwright() as p:
        # আসল ব্রাউজারের পরিচয় দেওয়া হচ্ছে
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        async def login():
            print(f"[{get_now()}] 🔑 লগিন করার চেষ্টা করছি (JS Injection Mode)...")
            try:
                # পেজ লোড হওয়া পর্যন্ত অপেক্ষা
                await page.goto(LOGIN_URL, wait_until="load", timeout=60000)
                await page.wait_for_timeout(2000)

                # সরাসরি জাভাস্ক্রিপ্ট ইঞ্জেক্ট করে লগিন (আপনার এক্সটেনশনের লজিক)
                login_success = await page.evaluate(f"""() => {{
                    try {{
                        const myUser = "{MY_USER}";
                        const myPass = "{MY_PASS}";
                        let inputs = document.querySelectorAll('input');
                        let userField, passField, ansField;
                        
                        inputs.forEach(inp => {{
                            let p = (inp.placeholder || "").toLowerCase();
                            if (inp.type === 'password') passField = inp;
                            else if (p.includes('user') || inp.type === 'text') {{ 
                                if (!userField && !p.includes('answer')) userField = inp; 
                            }}
                            if (p.includes('answer') || (inp.name || "").includes('ans')) ansField = inp;
                        }});

                        let match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                        let sum = match ? (parseInt(match[1]) + parseInt(match[2])) : "";

                        if (userField && passField && ansField && sum !== "") {{
                            userField.value = myUser; 
                            passField.value = myPass; 
                            ansField.value = sum;
                            
                            userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            ansField.dispatchEvent(new Event('input', {{ bubbles: true }}));

                            let btns = document.querySelectorAll('button, input[type="submit"]');
                            for(let b of btns) {{
                                if((b.innerText || b.value || "").toLowerCase().includes('login')) {{ 
                                    b.click(); 
                                    return true; 
                                }}
                            }}
                        }}
                        return false;
                    }} catch (e) {{
                        return false;
                    }}
                }}""")

                if login_success:
                    print(f"[{get_now()}] ✅ JS Injection সফল! লগিন বাটনে ক্লিক করা হয়েছে।")
                    await page.wait_for_timeout(5000)
                    if "login" not in page.url:
                        print(f"[{get_now()}] 🎉 লগিন সফল!")
                    else:
                        print(f"[{get_now()}] ⚠️ লগিন পেজেই আছে, তবে ফর্ম ফিল করা হয়েছে।")
                else:
                    print(f"[{get_now()}] ❌ JS Injection ব্যর্থ। ফর্ম ফিল্ড পাওয়া যায়নি।")

            except Exception as e:
                print(f"[{get_now()}] ❌ লগিন এরর: {str(e)}")

        # প্রথমবার লগিন ফাংশন কল
        await login()

        while True:
            # ৫ ঘণ্টা (১৮০০০ সেকেন্ড) হয়ে গেলে বট বন্ধ হবে যাতে গিটহাব নতুন শিডিউল শুরু করতে পারে
            if time.time() - START_TIME > 18000:
                print(f"[{get_now()}] 🔄 সেশন রিস্টার্ট হচ্ছে...")
                break

            try:
                # যদি সেশন আউট হয়ে যায় বা ভুল করে লগিন পেজে চলে যায়
                if "login" in page.url: 
                    await login()
                
                # মূল পেজে যাওয়া
                await page.goto(TARGET_URL, wait_until="load", timeout=60000)
                await page.wait_for_selector("table tbody tr", timeout=20000)
                
                rows = await page.query_selector_all("table tbody tr")
                found_new = False
                
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        num = (await cols[2].inner_text()).strip()
                        sms = (await cols[5].inner_text()).strip()
                        uid = f"{num}|{sms}"
                        
                        if uid not in sent_cache:
                            if send_telegram(num, sms):
                                sent_cache.add(uid)
                                found_new = True
                                # ক্যাশ লিমিট (মেমোরি বাঁচাতে)
                                if len(sent_cache) > 500: 
                                    sent_cache.pop()
                                    
                if found_new:
                    print(f"[{get_now()}] 📥 নতুন মেসেজ টেলিগ্রামে পাঠানো হয়েছে!")
                else:
                    print(f"[{get_now()}] ⏳ স্ক্যানিং সম্পন্ন। নতুন কোনো ডেটা নেই।")
                    
            except Exception as e:
                print(f"[{get_now()}] ⚠️ লুপ এরর (পুনরায় চেষ্টা চলছে): {str(e)}")
                try:
                    await page.reload()
                except:
                    pass
            
            # ৫ সেকেন্ড পর পর চেক করবে
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start_bot())
