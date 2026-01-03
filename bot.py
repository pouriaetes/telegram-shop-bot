# bot_webhook.py
"""
نسخه Webhook ربات — جایگزین bot.py
✅ تغییر مهم: حذف polling و ست کردن webhook اتومات با RAILWAY_PUBLIC_DOMAIN یا RENDER_EXTERNAL_URL
"""

import logging
import os
import time
from flask import Flask, request
import telebot
from telebot import types

from config import config
from database import Database
from accountmaker import AccountMakerHandlers, handle_account_maker_states
from help import HelpHandlers, handle_help_states
from payment_zibal import PaymentZibalHandlers, handle_payment_zibal_states
from payment_digital import PaymentDigitalHandlers, handle_payment_digital_states
from payment_admin import PaymentAdminHandlers, handle_payment_admin_states

from shared_state import user_states, user_data

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

bot = telebot.TeleBot(config.bot_token.get_secret_value(), parse_mode='Markdown', threaded=False)
telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 60

db = Database(config.database_path)

# register handlers
account_maker_handlers = AccountMakerHandlers(bot, db)
account_maker_handlers.register_handlers()

help_handlers = HelpHandlers(bot, db)
help_handlers.register_handlers()

payment_zibal_handlers = PaymentZibalHandlers(bot, db)
payment_zibal_handlers.register_handlers()

payment_digital_handlers = PaymentDigitalHandlers(bot, db)
payment_digital_handlers.register_handlers()

payment_admin_handlers = PaymentAdminHandlers(bot, db)
payment_admin_handlers.register_handlers()

# افزودن ادمین‌ها به دیتابیس
for admin_id in config.admin_list:
    db.get_or_create_user(admin_id, None, is_admin=True)

# helper functions
def is_admin(user_id: int) -> bool:
    return user_id in config.admin_list

def set_state(user_id: int, state: str):
    user_states[user_id] = state

def get_state(user_id: int):
    return user_states.get(user_id)

def clear_state(user_id: int):
    user_states.pop(user_id, None)
    user_data.pop(user_id, None)

# ===== handlers عمومی =====
@bot.message_handler(commands=['start'])
def cmd_start(message):
    clear_state(message.from_user.id)
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 لیست محصولات", callback_data="products_list"),
        types.InlineKeyboardButton("🎯 خرید اکانت سفارشی", callback_data="account_maker"),
        types.InlineKeyboardButton("💳 کیف پول", callback_data="wallet"),
        types.InlineKeyboardButton("📦 سفارش‌های من", callback_data="my_orders"),
        types.InlineKeyboardButton("💬 پشتیبانی", callback_data="help_support")
    )
    if is_admin(message.from_user.id):
        markup.add(types.InlineKeyboardButton("🔧 پنل ادمین", callback_data="admin_menu"))
    bot.send_message(message.chat.id, f"🌟 سلام {message.from_user.first_name} عزیز!\nبه فروشگاه خوش آمدید.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    clear_state(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 لیست محصولات", callback_data="products_list"),
        types.InlineKeyboardButton("🎯 خرید اکانت سفارشی", callback_data="account_maker"),
        types.InlineKeyboardButton("💳 کیف پول", callback_data="wallet"),
        types.InlineKeyboardButton("📦 سفارش‌های من", callback_data="my_orders"),
        types.InlineKeyboardButton("💬 پشتیبانی", callback_data="help_support")
    )
    if is_admin(call.from_user.id):
        markup.add(types.InlineKeyboardButton("🔧 پنل ادمین", callback_data="admin_menu"))
    try:
        bot.edit_message_text("🏠 منوی اصلی:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, "🏠 منوی اصلی:", reply_markup=markup)

# ... callbacks ساده برای products_list, wallet, my_orders, admin_menu
@bot.callback_query_handler(func=lambda call: call.data == "products_list")
def show_products(call):
    products = db.get_active_products()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for product in products:
        markup.add(types.InlineKeyboardButton(f"✅ {product['site_name']} - {product['stock_count']} عدد", callback_data=f"product_{product['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    bot.edit_message_text("🛒 لیست محصولات:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "wallet")
def show_wallet(call):
    user = db.get_or_create_user(call.from_user.id, call.from_user.username)
    balance = user.get('balance', 0)
    text = f"💳 کیف پول شما: {balance:,} تومان"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💳 پرداخت مستقیم", callback_data="payment_zibal"),
               types.InlineKeyboardButton("💎 پرداخت با ارز دیجیتال", callback_data="payment_digital"),
               types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "my_orders")
def show_orders(call):
    orders = db.get_user_orders(call.from_user.id)
    if not orders:
        bot.edit_message_text("📦 هنوز سفارشی ندارید.", call.message.chat.id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")))
        return
    text = "📦 سفارش‌های شما:\n\n"
    for o in orders[:10]:
        text += f"#{o['id']} - {o['site_name']} - {o['status']}\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")))

@bot.callback_query_handler(func=lambda call: call.data == "admin_menu")
def admin_menu(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛡️ مدیریت اکانت سفارشی", callback_data="admin_account_maker"))
    bot.edit_message_text("🔧 پنل ادمین", call.message.chat.id, call.message.message_id, reply_markup=markup)

# ===== message handler برای stateها =====
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    state = get_state(user_id)
    if not state:
        return
    # هر ماژول اگر state مربوطه را پردازش کرد True برگرداند
    if handle_account_maker_states(bot, db, message, user_id, state, user_data):
        return
    if handle_help_states(bot, db, message, user_id, state, user_data):
        return
    if handle_payment_zibal_states(bot, db, message, user_id, state, user_data):
        return
    if handle_payment_digital_states(bot, db, message, user_id, state, user_data):
        return
    if handle_payment_admin_states(bot, db, message, user_id, state, user_data):
        return
    # اگر هیچکدام پردازش نکردند، پیام را نادیده بگیر

# ===== webhook routes =====
@app.route('/', methods=['GET', 'HEAD'])
def index():
    return 'OK', 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        else:
            logger.warning("Invalid content type")
            return 'Invalid', 403
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return 'Error', 500

# ===== startup: set webhook automatically =====
if __name__ == '__main__':
    try:
        me = bot.get_me()
        logger.info(f"Bot @{me.username} connected")
        # تعیین آدرس webhook از env
        railway_url = os.environ.get('RAILWAY_PUBLIC_DOMAIN') or os.environ.get('RAILWAY_STATIC_URL')
        render_url = os.environ.get('RENDER_EXTERNAL_URL')
        webhook_url = None
        if railway_url:
            webhook_url = f"https://{railway_url}/webhook"  # ✅ تغییر مهم
        elif render_url:
            webhook_url = f"{render_url}/webhook"
        if webhook_url:
            bot.remove_webhook()
            time.sleep(1)
            res = bot.set_webhook(url=webhook_url, allowed_updates=['message','callback_query'])
            logger.info(f"Webhook set to {webhook_url}, result={res}")
            wi = bot.get_webhook_info()
            logger.info(f"Webhook info: url={wi.url} pending={wi.pending_update_count}")
        else:
            logger.warning("No public domain found. Set RAILWAY_PUBLIC_DOMAIN or RENDER_EXTERNAL_URL.")
    except Exception as e:
        logger.error("Error while starting bot", exc_info=True)
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
