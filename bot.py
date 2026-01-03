import telebot
from telebot import types
import logging
from config import config
from database import Database
from accountmaker import AccountMakerHandlers, handle_account_maker_states
from help import HelpHandlers, handle_help_states
from payment_zibal import PaymentZibalHandlers, handle_payment_zibal_states
from payment_digital import PaymentDigitalHandlers, handle_payment_digital_states
from payment_admin import PaymentAdminHandlers, handle_payment_admin_states
from flask import Flask, request
import os

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ایجاد Flask app
app = Flask(__name__)

# ایجاد بات
bot = telebot.TeleBot(
    config.bot_token.get_secret_value(),
    parse_mode='Markdown',
    threaded=False
)

# تنظیم timeout
telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 60

# ایجاد دیتابیس
db = Database(config.database_path)

# ثبت handlers
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

# افزودن ادمین‌ها
for admin_id in config.admin_list:
    db.get_or_create_user(admin_id, None, is_admin=True)

# دیکشنری state management
user_states = {}
user_data = {}

def is_admin(user_id: int) -> bool:
    return user_id in config.admin_list

def set_state(user_id: int, state: str):
    user_states[user_id] = state

def get_state(user_id: int) -> str:
    return user_states.get(user_id, None)

def clear_state(user_id: int):
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]

# ===== USER HANDLERS ===== (تمام handlerهای قبلی شما)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    clear_state(message.from_user.id)
    user = db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )
    
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
    
    bot.send_message(
        message.chat.id,
        f"🌟 سلام {message.from_user.first_name} عزیز!\n\n"
        f"به فروشگاه zentro خوش آمدید.\n"
        f"برای شروع، یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=markup
    )

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
    
    bot.edit_message_text(
        "🏠 منوی اصلی:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# ... باقی handlerهای شما (products_list, wallet, my_orders, admin_menu و غیره)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    state = get_state(user_id)
    
    if not state:
        return
    
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
    
    # باقی state handlerهای شما...

# ===== WEBHOOK ROUTES =====

@app.route('/', methods=['GET'])
def index():
    return 'Bot is running!', 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت پیام‌های تلگرام"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Invalid content type', 403

# ===== راه‌اندازی =====
if __name__ == '__main__':
    import time
    
    logger.info("=" * 50)
    logger.info("🤖 ربات در حال راه‌اندازی (Webhook Mode)...")
    logger.info("=" * 50)
    
    try:
        bot_info = bot.get_me()
        logger.info(f"✅ ربات متصل شد: @{bot_info.username}")
        
        # دریافت URL از Railway
        railway_url = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
        
        if railway_url:
            webhook_url = f"https://{railway_url}/webhook"
            
            # حذف webhook قدیمی
            bot.remove_webhook()
            time.sleep(1)
            
            # تنظیم webhook جدید
            result = bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook تنظیم شد: {webhook_url}")
            logger.info(f"📊 نتیجه: {result}")
            
            # بررسی وضعیت
            webhook_info = bot.get_webhook_info()
            logger.info(f"📊 Webhook Info: URL={webhook_info.url}")
            
        else:
            logger.error("❌ RAILWAY_PUBLIC_DOMAIN یافت نشد!")
            logger.info("💡 Railway باید یک Public Domain تولید کند")
            exit(1)
        
    except Exception as e:
        logger.error(f"❌ خطا در تنظیم webhook: {e}")
        exit(1)
    
    logger.info("🚀 ربات آماده دریافت پیام است!")
    logger.info("=" * 50)
    
    # اجرای Flask
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
