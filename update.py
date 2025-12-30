#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
حالت تعمیر و نگهداری ربات
Bot Maintenance Mode
"""

import os
import logging
import telebot
from telebot import types
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from datetime import datetime

# ===== تنظیمات =====
class Settings(BaseSettings):
    bot_token: SecretStr
    admin_ids: str = ""
    proxy_url: str | None = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = Settings()

# ===== لاگر =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== ربات =====
bot = telebot.TeleBot(
    config.bot_token.get_secret_value(),
    parse_mode='Markdown'
)

# تنظیم پروکسی
if config.proxy_url:
    from telebot import apihelper
    apihelper.proxy = {
        'http': config.proxy_url,
        'https': config.proxy_url
    }
    logger.info("🔐 پروکسی فعال است")

# لیست ادمین‌ها
ADMIN_IDS = [int(x.strip()) for x in config.admin_ids.split(',') if x.strip()]

def is_admin(user_id: int) -> bool:
    """بررسی ادمین بودن"""
    return user_id in ADMIN_IDS

# ===== پیام تعمیر و نگهداری =====
MAINTENANCE_MESSAGE = """
سلام **{name}**! 👋

متأسفانه به خاطر **نوسانات شدید دلار** و تغییرات لحظه‌ای قیمت‌ها، ربات رو **موقتاً خاموش** کردیم.

⏳ **تا کی؟** تا وقتی اوضاع آروم بشه و همه چیز رو بروزرسانی کنیم.

چرا این اتفاق افتاد؟
• نوسانات بی‌سابقه دلار
• تنظیم قیمت‌های جدید
• بهبود و بهینه‌سازی سیستم

قول می‌دیم به محض اینکه همه چیز آماده شد، **از همین ربات** بهتون خبر بدیم!

🙏 واقعاً از **صبر و همراهی‌تون** ممنونیم ❤️

━━━━━━━━━━━━━━━━
🌟 تیم پشتیبانی
"""

ADMIN_PANEL_MESSAGE = """
🔧 **پنل مدیریت - حالت تعمیر**

ربات در حال حاضر در **حالت تعمیر و نگهداری** است.

📊 **وضعیت:** 🔴 غیرفعال
⏰ **از تاریخ:** {}
👥 **تعداد کاربران مسدود شده:** همه

━━━━━━━━━━━━━━━━━━━━━

برای فعال‌سازی مجدد، Start Command را به `python bot.py` تغییر دهید.
"""

# ===== آمار =====
blocked_users = set()
start_time = datetime.now()

# ===== Handlers =====

@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    """پاسخ به دستور start"""
    user_id = message.from_user.id
    user_name = message.from_user.first_name or message.from_user.username or "دوست عزیز"
    
    blocked_users.add(user_id)
    
    logger.info(f"🚫 کاربر {user_name} ({user_id}) سعی در استفاده کرد")
    
    if is_admin(user_id):
        # پیام ویژه ادمین
        admin_msg = MAINTENANCE_MESSAGE.format(name=user_name) + "\n\n⚡ **شما ادمین هستید - دسترسی محدود دارید**"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📊 آمار", callback_data="admin_stats"))
        
        bot.send_message(
            message.chat.id,
            admin_msg,
            reply_markup=markup
        )
    else:
        # پیام عادی
        bot.send_message(
            message.chat.id,
            MAINTENANCE_MESSAGE.format(name=user_name)
        )

@bot.message_handler(commands=['admin', 'panel'])
def handle_admin(message):
    """پنل ادمین"""
    if not is_admin(message.from_user.id):
        user_name = message.from_user.first_name or message.from_user.username or "دوست عزیز"
        bot.send_message(
            message.chat.id,
            MAINTENANCE_MESSAGE.format(name=user_name)
        )
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📊 آمار تعمیرات", callback_data="admin_stats"))
    markup.add(types.InlineKeyboardButton("📋 لیست کاربران مسدود", callback_data="admin_blocked"))
    
    bot.send_message(
        message.chat.id,
        ADMIN_PANEL_MESSAGE.format(start_time.strftime("%Y-%m-%d %H:%M:%S")),
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """پاسخ به تمام پیام‌ها"""
    user_id = message.from_user.id
    user_name = message.from_user.first_name or message.from_user.username or "دوست عزیز"
    
    blocked_users.add(user_id)
    
    logger.info(f"🚫 پیام از {user_name} ({user_id}): {message.text[:50] if message.text else 'N/A'}")
    
    bot.send_message(
        message.chat.id,
        MAINTENANCE_MESSAGE.format(name=user_name)
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    """پاسخ به callback ها"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "🔧 ربات در حال تعمیر است",
            show_alert=True
        )
        return
    
    if call.data == "admin_stats":
        # آمار
        uptime = datetime.now() - start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        stats_text = f"""
📊 **آمار حالت تعمیر**

⏰ **مدت زمان تعطیلی:** {hours} ساعت و {minutes} دقیقه
👥 **تعداد کاربران مسدود شده:** {len(blocked_users)}
🕐 **شروع تعمیر:** {start_time.strftime("%Y-%m-%d %H:%M:%S")}

━━━━━━━━━━━━━━━━━━━━━
🔴 **وضعیت:** غیرفعال
"""
        
        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=call.message.reply_markup
        )
    
    elif call.data == "admin_blocked":
        # لیست کاربران
        if blocked_users:
            users_list = "\n".join([f"• {uid}" for uid in list(blocked_users)[:20]])
            if len(blocked_users) > 20:
                users_list += f"\n\n... و {len(blocked_users) - 20} کاربر دیگر"
        else:
            users_list = "هیچ کاربری سعی در استفاده نکرده"
        
        blocked_text = f"""
📋 **کاربران مسدود شده**

{users_list}

━━━━━━━━━━━━━━━━━━━━━
📊 **مجموع:** {len(blocked_users)} کاربر
"""
        
        bot.edit_message_text(
            blocked_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=call.message.reply_markup
        )
    
    bot.answer_callback_query(call.id)

# ===== Health Check =====
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return {
        'status': 'maintenance',
        'message': 'Bot is under maintenance',
        'blocked_users': len(blocked_users),
        'uptime_seconds': (datetime.now() - start_time).total_seconds()
    }, 200

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ===== اجرا =====
if __name__ == '__main__':
    try:
        # شروع health check server
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("✅ Health check server started on port " + os.getenv('PORT', '8080'))
        
        logger.info("="*60)
        logger.info("🔧 ربات در حالت تعمیر و نگهداری است")
        logger.info(f"⏰ شروع: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        # شروع polling
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 ربات متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطا: {e}")
        import traceback
        traceback.print_exc()
        raise
