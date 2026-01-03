import telebot
from config import config
import time

# ایجاد بات
bot = telebot.TeleBot(config.bot_token.get_secret_value())

print("🔄 در حال ریست کردن بات...")

try:
    # حذف webhook با تمام پارامترها
    result = bot.delete_webhook(drop_pending_updates=True)
    print(f"✅ Webhook حذف شد: {result}")
    
    # صبر 3 ثانیه
    time.sleep(3)
    
    # بررسی وضعیت
    webhook_info = bot.get_webhook_info()
    print(f"📊 وضعیت فعلی:")
    print(f"  - URL: {webhook_info.url}")
    print(f"  - Pending updates: {webhook_info.pending_update_count}")
    
    if webhook_info.url:
        print("⚠️ Webhook هنوز فعال است!")
        # تلاش مجدد
        bot.remove_webhook()
        time.sleep(2)
        bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook دوباره حذف شد")
    else:
        print("✅ بات آماده است - می‌توانید bot.py را اجرا کنید")
    
except Exception as e:
    print(f"❌ خطا: {e}")
