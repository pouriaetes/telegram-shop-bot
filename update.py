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
🔧 **ربات در حال تعمیر و نگهداری است**

⚠️ به دلیل **نوسانات شدید دلار** و تغییرات قیمت‌های لحظه‌ای، ربات به صورت **موقت غیرفعال** شده است.

┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🕐 **زمان تعطیلی:**        
┃  تا اطلاع ثانوی            
┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛

📌 **دلایل تعطیلی:**
• نوسانات شدید نرخ دلار
• به‌روزرسانی قیمت‌ها
• بهینه‌سازی سیستم

💬 **اطلاع‌رسانی:**
به محض برطرف شدن مشکلات، از طریق همین ربات به شما اطلاع‌رسانی خواهد شد.

🙏 از **صبر و شکیبایی** شما بسیار سپاسگزاریم.

━━━━━━━━━━━━━━━━━━━━━
🌟 **تیم پشتیبانی**
"""

ADMIN_PANEL_MESSAGE = """
🔧 **پنل مدیریت - حالت تعمیر**

ربات در حال حاضر در **حالت تعمیر و نگهداری** است.

📊 **وضعیت:** 🔴 غیرفعال
⏰ **از تاریخ:** {}
👥 **تعداد کاربران مسدود شده:** همه

━━━━━━━━━━━━━━━━━━━━━

برای فعال‌سازی مجدد، فایل `bot.py` را اجرا کنید.
"""

# ===== آمار =====
blocked_users = set()
start_time = datetime.now()

# ===== Handlers =====

@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    """پاسخ به دستور start"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    blocked_users.add(user_id)
    
    logger.info(f"🚫 کاربر {username} ({user_id}) سعی در استفاده کرد")
    
    if is_admin(user_id):
        # پیام ویژه ادمین
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📊 آمار", callback_data="admin_stats"))
        
        bot.send_message(
            message.chat.id,
            MAINTENANCE_MESSAGE + "\n\n⚡ **شما ادمین هستید - دسترسی محدود دارید**",
            reply_markup=markup
        )
    else:
        # پیام عادی
        bot.send_message(
            message.chat.id,
            MAINTENANCE_MESSAGE
        )

@bot.message_handler(commands=['admin', 'panel'])
def handle_admin(message):
    """پنل ادمین"""
    if not is_admin(message.from_user.id):
        bot.send_message(
            message.chat.id,
            MAINTENANCE_MESSAGE
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
    username = message.from_user.username or message.from_user.first_name
    
    blocked_users.add(user_id)
    
    logger.info(f"🚫 پیام از {username} ({user_id}): {message.text[:50] if message.text else 'N/A'}")
    
    bot.send_message(
        message.chat.id,
        MAINTENANCE_MESSAGE
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
    app.run(host='0.0.0.0', port=port)

# ===== اجرا =====
if __name__ == '__main__':
    try:
        # شروع health check server
        Thread(target=run_flask, daemon=True).start()
        logger.info("✅ Health check server started")
        
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
        raise
