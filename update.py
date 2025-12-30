#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت ارسال پیام به تمام کاربران
استفاده: python update.py
"""

import sqlite3
import time
import os
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

# ===== تنظیمات =====
class Settings(BaseSettings):
    bot_token: SecretStr
    database_path: str = os.getenv("DATABASE_PATH", "shop.db")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = Settings()

# ===== پیام برای ارسال =====
MESSAGE_TEXT = """
🔔 **اطلاعیه مهم**

سلام {name} عزیز 👋

متأسفانه به دلیل **نوسانات شدید دلار** و تغییرات قیمت، ربات **موقتاً غیرفعال** شده است.

⏳ **تا اطلاع ثانوی** ربات در دسترس نخواهد بود.

🙏 از صبر و همراهی شما بسیار سپاسگزاریم.

💬 برای پیگیری و دریافت اطلاعات بیشتر با پشتیبانی تماس بگیرید.

با تشکر
تیم پشتیبانی 🌟
"""

# ===== توابع =====
def find_database():
    """پیدا کردن مسیر دیتابیس"""
    possible_paths = [
        config.database_path,
        "/app/shop.db",
        "/data/shop.db",
        "shop.db",
        "/workspace/shop.db",
        os.path.join(os.getcwd(), "shop.db")
    ]
    
    print("🔍 جستجوی دیتابیس...")
    for path in possible_paths:
        if os.path.exists(path):
            print(f"✅ دیتابیس پیدا شد: {path}")
            return path
        else:
            print(f"   ❌ یافت نشد: {path}")
    
    return None

def get_all_users(db_path):
    """دریافت تمام کاربران از دیتابیس"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT telegram_id, username FROM users")
        users = cursor.fetchall()
        conn.close()
        return users
    except Exception as e:
        print(f"❌ خطا در خواندن دیتابیس: {e}")
        return []

def send_message_via_api(telegram_id, text):
    """ارسال پیام از طریق Telegram API"""
    import requests
    
    token = config.bot_token.get_secret_value()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    data = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json().get("ok", False)
    except Exception as e:
        print(f"   ❌ خطا: {e}")
        return False

def main():
    """اجرای اصلی"""
    print("="*60)
    print("🚀 شروع ارسال پیام به کاربران")
    print("="*60)
    
    # Debug info
    print(f"\n📊 اطلاعات محیط:")
    print(f"   Working directory: {os.getcwd()}")
    print(f"   DATABASE_PATH env: {os.getenv('DATABASE_PATH', 'NOT SET')}")
    
    # پیدا کردن دیتابیس
    db_path = find_database()
    
    if not db_path:
        print("\n❌ دیتابیس یافت نشد!")
        print("\n💡 راهنمایی:")
        print("   1. مطمئن شوید DATABASE_PATH در environment variables تنظیم شده")
        print("   2. یا دیتابیس در یکی از مسیرهای بالا وجود دارد")
        sys.exit(1)
    
    # دریافت کاربران
    print("\n📊 در حال دریافت لیست کاربران...")
    users = get_all_users(db_path)
    
    if not users:
        print("⚠️ هیچ کاربری یافت نشد!")
        sys.exit(1)
    
    print(f"✅ تعداد کاربران: {len(users)}")
    
    # ارسال پیام‌ها
    print("\n📨 شروع ارسال...")
    print("-"*60)
    
    success_count = 0
    failed_count = 0
    
    for idx, user in enumerate(users, 1):
        telegram_id = user['telegram_id']
        username = user['username'] or "کاربر"
        
        message = MESSAGE_TEXT.format(name=username)
        
        print(f"\n[{idx}/{len(users)}] 📤 ارسال به: {username} (ID: {telegram_id})")
        
        success = send_message_via_api(telegram_id, message)
        
        if success:
            print(f"   ✅ ارسال موفق")
            success_count += 1
        else:
            print(f"   ❌ ارسال ناموفق")
            failed_count += 1
        
        if idx < len(users):
            time.sleep(0.5)
    
    # نتیجه نهایی
    print("\n" + "="*60)
    print("📊 نتیجه ارسال:")
    print("="*60)
    print(f"✅ موفق: {success_count}")
    print(f"❌ ناموفق: {failed_count}")
    print(f"📊 کل: {len(users)}")
    print("="*60)
    print("\n✅ اتمام عملیات!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ عملیات توسط کاربر لغو شد.")
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
