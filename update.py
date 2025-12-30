#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
حالت تعمیر و نگهداری ربات - نسخه Webhook
Bot Maintenance Mode - Webhook Version
"""

import os
import logging
import telebot
from telebot import types
from flask import Flask, request
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from datetime import datetime

# ===== تنظیمات =====
class Settings(BaseSettings):
    bot_token: SecretStr
    admin_ids: str = ""
    
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
    parse_mode='Markdown',
    threaded=False
)

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

قول می‌دیم به محض اینکه همه چیز آماده شد، **از همین ربات** بهتون خبر بدیم!

🙏 واقعاً از **صبر و همراهی‌تون** ممنونیم ❤️


تیم پشتیبانی
"""

ADMIN_PANEL_MESSAGE = """
🔧 **پنل مدیریت - حالت تعمیر**

ربات در حال حاضر در **حالت تعمیر و نگهداری** است.

📊 **وضعیت:** 🔴 غیرفعال
⏰ **از تاریخ:** {}
👥 **کاربران مسدود شده:** {}

━━━━━━━━━━━━━━━━━━━━━

برای فعال‌سازی مجدد، Start Command را به `python bot.py` تغییر دهید.
"""

# ===== آمار =====
blocked_users = set()
start_time = datetime.now()

# ===== Flask App =====
app = Flask(__name__)

# ===== Handlers =====

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
        ADMIN_PANEL_MESSAGE.format(
            start_time.strftime("%Y-%m-%d %H:%M:%S"),
            len(blocked_users)
        ),
        reply_markup=markup
    )

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

# ===== Process Update =====
def process_update(update):
    """پردازش هر update"""
    try:
        if update.message:
            message = update.message
            
            # بررسی command ها
            if message.text:
                if message.text.startswith('/start') or message.text.startswith('/help'):
                    handle_start(message)
                elif message.text.startswith('/admin') or message.text.startswith('/panel'):
                    handle_admin(message)
                else:
                    handle_all_messages(message)
            else:
                handle_all_messages(message)
        
        elif update.callback_query:
            handle_callbacks(update.callback_query)
            
    except Exception as e:
        logger.error(f"❌ خطا در پردازش update: {e}")

# ===== Flask Routes =====

@app.route('/', methods=['GET'])
def index():
    return {
        'status': 'maintenance',
        'message': 'Bot is under maintenance - ربات در حال تعمیر است',
        'blocked_users': len(blocked_users),
        'uptime_hours': (datetime.now() - start_time).total_seconds() / 3600
    }, 200

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت update ها از تلگرام"""
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        process_update(update)
        return '', 200
    except Exception as e:
        logger.error(f"❌ خطا در webhook: {e}")
        return '', 500

# ===== Setup Webhook =====
def setup_webhook():
    """تنظیم webhook"""
    try:
        # حذف webhook قبلی
        bot.remove_webhook()
        logger.info("✅ Webhook قبلی حذف شد")
        
        # دریافت URL از Railway
        railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_STATIC_URL')
        
        if railway_domain:
            webhook_url = f"https://{railway_domain}/webhook"
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook تنظیم شد: {webhook_url}")
        else:
            logger.warning("⚠️ RAILWAY_PUBLIC_DOMAIN یافت نشد - از polling استفاده می‌شود")
            
    except Exception as e:
        logger.error(f"❌ خطا در تنظیم webhook: {e}")

# ===== اجرا =====
if __name__ == '__main__':
    try:
        logger.info("="*60)
        logger.info("🔧 ربات در حالت تعمیر و نگهداری است")
        logger.info(f"⏰ شروع: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        # تنظیم webhook
        setup_webhook()
        
        # اجرای Flask
        port = int(os.getenv('PORT', 8080))
        logger.info(f"🚀 Flask server starting on port {port}")
        
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        logger.info("\n🛑 ربات متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطا: {e}")
        import traceback
        traceback.print_exc()
