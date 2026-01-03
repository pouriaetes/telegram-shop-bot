باشه! الان تمام فایل‌های کامل را برای Webhook آماده می‌کنم 🚀

📁 فایل‌های کامل برای Webhook
1. bot_webhook.py (فایل اصلی)
python
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

# ===== USER HANDLERS =====

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
    bot.edit_message_text("🏠 منوی اصلی:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "products_list")
def show_products(call):
    products = db.get_active_products()
    if not products:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
        bot.edit_message_text("❌ در حال حاضر محصولی موجود نیست.", call.message.chat.id, call.message.message_id, reply_markup=markup)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for product in products:
        stock_emoji = "✅" if product['stock_count'] > 0 else "❌"
        button_text = f"{stock_emoji} {product['site_name']} ({product['stock_count']} عدد)"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"product_{product['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    bot.edit_message_text("🛒 لیست محصولات موجود:\n\nمحصول مورد نظر خود را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "wallet")
def show_wallet(call):
    user_id = call.from_user.id
    clear_state(user_id)
    user = db.get_or_create_user(user_id, call.from_user.username)
    balance = user['balance']
    text = f"💳 **کیف پول شما**\n\n💰 موجودی: {balance:,} تومان\n\nبرای شارژ کیف پول، یکی از روش‌های پرداخت را انتخاب کنید:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 پرداخت مستقیم", callback_data="payment_zibal"),
        types.InlineKeyboardButton("💎 پرداخت با ارز دیجیتال", callback_data="payment_digital"),
        types.InlineKeyboardButton("📜 تاریخچه تراکنش‌ها", callback_data="transactions_history"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "my_orders")
def show_orders(call):
    orders = db.get_user_orders(call.from_user.id)
    if not orders:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
        bot.edit_message_text("📦 شما هنوز سفارشی ثبت نکرده‌اید.", call.message.chat.id, call.message.message_id, reply_markup=markup)
        return
    text = "📦 **سفارش‌های شما:**\n\n"
    for order in orders[:10]:
        status_emoji = {"delivered": "✅", "pending": "⏳", "cancelled": "❌"}.get(order['status'], "❓")
        text += f"{status_emoji} سفارش #{order['id']}\n📦 محصول: {order['site_name']}\n💰 مبلغ: {order['price']:,.0f} تومان\n📅 تاریخ: {order['created_at']}\n\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_menu")
def show_admin_menu(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
        return
    clear_state(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add_product"),
        types.InlineKeyboardButton("🛡️ مدیریت اکانت سفارشی", callback_data="admin_account_maker"),
        types.InlineKeyboardButton("📦 افزودن اکانت", callback_data="admin_add_account"),
        types.InlineKeyboardButton("📊 مدیریت محصولات", callback_data="admin_manage_products"),
        types.InlineKeyboardButton("💰 افزایش موجودی کاربر", callback_data="admin_add_balance"),
        types.InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data="admin_payments"),
        types.InlineKeyboardButton("🎫 پنل پشتیبانی", callback_data="admin_support_panel"),
        types.InlineKeyboardButton("📈 آمار فروش", callback_data="admin_statistics"),
        types.InlineKeyboardButton("👤 منوی کاربر", callback_data="back_to_main")
    )
    bot.edit_message_text("🔧 **پنل مدیریت**\n\nیکی از گزینه‌های زیر را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_statistics")
def show_statistics(call):
    if not is_admin(call.from_user.id):
        return
    stats = db.get_detailed_statistics()
    text = (
        f"📈 **آمار کامل فروشگاه**\n\n"
        f"👥 **کاربران:**\n  • کاربران واقعی: {stats['real_users']}\n  • ادمین‌ها: {stats['admin_count']}\n  • مجموع: {stats['total_users']}\n\n"
        f"📦 **محصولات:**\n  • فعال: {stats['active_products']}\n  • غیرفعال: {stats['total_products'] - stats['active_products']}\n  • مجموع: {stats['total_products']}\n\n"
        f"🔑 **اکانت‌ها:**\n  • موجود: {stats['available_accounts']}\n  • فروخته شده: {stats['sold_accounts']}\n\n"
        f"💰 **فروش:**\n  • تعداد فروش: {stats['total_sales']}\n  • درآمد کل: {stats['total_revenue']:,.0f} تومان"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_statistics"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

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

# ===== WEBHOOK ROUTES =====

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return 'Bot is running!', 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت پیام‌های تلگرام"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        else:
            logger.warning(f"Invalid content type: {request.headers.get('content-type')}")
            return 'Invalid content type', 403
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return 'Error', 500

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
        railway_url = os.environ.get('RAILWAY_PUBLIC_DOMAIN') or os.environ.get('RAILWAY_STATIC_URL')
        render_url = os.environ.get('RENDER_EXTERNAL_URL')
        
        webhook_url = None
        if railway_url:
            webhook_url = f"https://{railway_url}/webhook"
        elif render_url:
            webhook_url = f"{render_url}/webhook"
        
        if webhook_url:
            # حذف webhook قدیمی
            bot.remove_webhook()
            time.sleep(1)
            
            # تنظیم webhook جدید
            result = bot.set_webhook(url=webhook_url, allowed_updates=['message', 'callback_query'])
            logger.info(f"✅ Webhook تنظیم شد: {webhook_url}")
            logger.info(f"📊 نتیجه: {result}")
            
            # بررسی وضعیت
            webhook_info = bot.get_webhook_info()
            logger.info(f"📊 Webhook URL: {webhook_info.url}")
            logger.info(f"📊 Pending updates: {webhook_info.pending_update_count}")
            
        else:
            logger.error("❌ هیچ URL عمومی یافت نشد!")
            logger.info("💡 لطفاً در Railway یا Render یک Public Domain تولید کنید")
        
    except Exception as e:
        logger.error(f"❌ خطا در تنظیم webhook: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("🚀 ربات آماده دریافت پیام است!")
    logger.info("=" * 50)
    
    # اجرای Flask
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
2. accountmaker.py (اصلاح شده با ارسال به ادمین)
python
"""
ماژول خرید اکانت سفارشی (Account Maker)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List
from telebot import types
import json
import time

logger = logging.getLogger(__name__)

# ذخیره سفارشات موقت
pending_orders = {}
order_counter = 1

# اطلاعات محصول ChatGPT GO
CHATGPT_GO_PRODUCT = {
    "name": "🛡️ ChatGPT GO",
    "description": """این اکانت کرک شده است و به همین دلیل، قیمت آن پایینتر از قیمت اصلی سایت رسمی میباشد.""",
    "rules": """📋 قوانین:
1. این حساب هیچ پشتیبانیای ندارد (به جز در هفته اول، تنها در صورت غیرفعال شدن حساب).
2. این حساب یک حساب کاربری معمولی است که مستقیماً از OpenAI دریافت شده؛ بنابراین، حتماً از VPN معتبر استفاده کنید.
3. استفاده همزمان چندین کاربر از این حساب ممکن است در طول زمان منجر به مسدود شدن حساب شما شود (هیچ گونه پشتیبانی یا بازگشت وجه وجود نخواهد داشت).
4. این حساب به مدت یک سال برای شما فعال خواهد بود.
5. این حساب روی ایمیل شخصی شما ساخته و فعال میشود؛ فقط باید روی آن ایمیل هیچ حسابی از قبل وجود نداشته باشد (برای امنیت بیشتر بهتر است از یک ایمیل جدید استفاده کنید).
6. این حساب به قیمت 1,499,000 تومان به فروش میرسد.""",
    "price": 1499000,
    "delivery_time": 5
}

# ===== HANDLERS =====

class AccountMakerHandlers:
    """handlers برای Account Maker"""
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    def register_handlers(self):
        """ثبت handlers"""
        # User handlers
        self.bot.callback_query_handler(func=lambda c: c.data == "account_maker")(self.show_account_types)
        self.bot.callback_query_handler(func=lambda c: c.data == 'chatgpt_go_start_purchase')(self.start_purchase_flow)
        self.bot.callback_query_handler(func=lambda c: c.data == "my_custom_orders")(self.show_my_orders)
        
        # Admin handlers
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_account_maker")(self.admin_menu)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_acc_pending_orders")(self.admin_pending_orders)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_order_"))(self.admin_show_order)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_approve_"))(self.admin_approve_order)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_reject_"))(self.admin_reject_order)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_send_"))(self.admin_deliver_order)
    
    def show_account_types(self, call):
        """نمایش ChatGPT GO"""
        product = CHATGPT_GO_PRODUCT
        text = f"""{product['name']}

📝 توضیحات:
{product['description']}

{product['rules']}

💰 قیمت: {product['price']:,} تومان

⏱ زمان تحویل: حداکثر {product['delivery_time']} ساعت"""
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ ادامه خرید", callback_data='chatgpt_go_start_purchase'))
        markup.add(types.InlineKeyboardButton("📦 سفارشات من", callback_data='my_custom_orders'))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main'))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def start_purchase_flow(self, call):
        """شروع فرآیند خرید ChatGPT GO"""
        global order_counter, pending_orders
        
        user_id = call.from_user.id
        order_id = f"CGPT_{order_counter}_{int(time.time())}"
        order_counter += 1
        
        pending_orders[order_id] = {
            'user_id': user_id,
            'username': call.from_user.username,
            'status': 'waiting_email',
            'created_at': time.time(),
            'product': 'ChatGPT GO'
        }
        
        from bot_webhook import user_data, set_state
        user_data[user_id] = {'order_id': order_id}
        set_state(user_id, 'chatgpt_go_waiting_email')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data='account_maker'))
        
        self.bot.send_message(
            call.message.chat.id,
            f"""📧 **مرحله 1 از 4: ارسال ایمیل**

لطفاً ایمیل خود را ارسال کنید:

⚠️ این ایمیل نباید قبلاً در OpenAI ثبت شده باشد
⚠️ از یک ایمیل جدید برای امنیت بیشتر استفاده کنید""",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def show_my_orders(self, call):
        """نمایش سفارشات کاربر"""
        user_id = call.from_user.id
        user_orders = [(order_id, order) for order_id, order in pending_orders.items() if order['user_id'] == user_id]
        
        if not user_orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="account_maker"))
            self.bot.edit_message_text("📦 شما هنوز سفارشی ثبت نکرده‌اید.", call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        
        text = "📦 **سفارشات ChatGPT GO شما:**\n\n"
        status_text = {
            'waiting_email': '📧 در انتظار ایمیل',
            'waiting_password': '🔐 در انتظار پسورد',
            'waiting_admin_approval': '⏳ در انتظار تایید ادمین',
            'preparing': '🔄 در حال آماده‌سازی',
            'delivered': '✅ تحویل داده شد',
            'rejected': '❌ رد شد'
        }
        
        for order_id, order in user_orders[:5]:
            text += f"🆔 {order_id}\n"
            text += f"📧 ایمیل: {order.get('email', 'NA')}\n"
            text += f"💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان\n"
            text += f"📊 وضعیت: {status_text.get(order['status'], order['status'])}\n"
            text += f"📅 تاریخ: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}\n\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="account_maker"))
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_menu(self, call):
        """منوی ادمین برای Account Maker"""
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📋 سفارشات در انتظار", callback_data="admin_acc_pending_orders"),
            types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_menu")
        )
        self.bot.edit_message_text("🛡️ **مدیریت اکانت سفارشی**", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_pending_orders(self, call):
        """نمایش سفارشات در انتظار"""
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            return
        
        orders = {order_id: order for order_id, order in pending_orders.items() if order['status'] in ['waiting_admin_approval', 'preparing']}
        
        if not orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
            self.bot.edit_message_text("✅ سفارشی در انتظار نیست.", call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        
        text = f"📋 **سفارشات در انتظار: {len(orders)} عدد**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for order_id, order in list(orders.items())[:10]:
            status_emoji = {'waiting_admin_approval': '⏳', 'preparing': '🔄'}.get(order['status'], '❓')
            button_text = f"{status_emoji} {order_id} - {order.get('email', 'NA')[:20]}..."
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f"admin_acc_order_{order_id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_show_order(self, call):
        """نمایش جزئیات سفارش"""
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            return
        
        order_id = call.data.replace("admin_acc_order_", "")
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        order = pending_orders[order_id]
        status_text = {
            'waiting_admin_approval': '⏳ در انتظار تایید',
            'preparing': '🔄 در حال آماده‌سازی',
            'delivered': '✅ تحویل داده شد',
            'rejected': '❌ رد شد'
        }
        
        text = f"""📋 **جزئیات سفارش**

🆔 شماره: {order_id}
👤 کاربر: @{order.get('username', 'ناشناس')} (ID: {order['user_id']})
🎮 محصول: {order['product']}

📧 ایمیل: {order.get('email', 'NA')}
🔐 پسورد: {order.get('password', 'NA')}

💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان
📊 وضعیت: {status_text.get(order['status'], order['status'])}
📅 تاریخ: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}"""
        
        if order.get('account_info'):
            text += f"\n\n📋 اطلاعات ارسال شده:\n{order['account_info']}"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        if order['status'] == 'waiting_admin_approval':
            markup.row(
                types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_acc_approve_{order_id}"),
                types.InlineKeyboardButton("❌ رد", callback_data=f"admin_acc_reject_{order_id}")
            )
        elif order['status'] == 'preparing':
            markup.add(types.InlineKeyboardButton("📤 ارسال اکانت", callback_data=f"admin_acc_send_{order_id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_acc_pending_orders"))
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_approve_order(self, call):
        """تایید سفارش توسط ادمین"""
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        order_id = call.data.replace("admin_acc_approve_", "")
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        order = pending_orders[order_id]
        if order['status'] != 'waiting_admin_approval':
            self.bot.answer_callback_query(call.id, "⚠️ این سفارش قبلاً پردازش شده!", show_alert=True)
            return
        
        order['status'] = 'preparing'
        order['approved_by'] = call.from_user.id
        order['approved_at'] = time.time()
        
        updated_text = f"""✅ **سفارش تایید شد!**

🆔 {order_id}
👤 User ID: {order['user_id']}
📧 {order['email']}

تایید شده توسط: {call.from_user.first_name}
⏰ {time.strftime('%H:%M:%S')}

اکانت را آماده و ارسال کنید."""
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 ارسال اکانت", callback_data=f"admin_acc_send_{order_id}"))
        
        try:
            self.bot.edit_message_text(updated_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        except:
            pass
        
        self.bot.send_message(
            order['user_id'],
            f"""✅ **سفارش شما تایید شد!**

🆔 شماره سفارش: {order_id}

⏳ اکانت شما در حال آماده‌سازی است.
زمان تحویل: حداکثر {CHATGPT_GO_PRODUCT['delivery_time']} ساعت

پس از آماده شدن، به شما اطلاع داده می‌شود."""
        )
        
        self.bot.answer_callback_query(call.id, "✅ سفارش تایید شد!", show_alert=True)
    
    def admin_reject_order(self, call):
        """رد سفارش"""
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        order_id = call.data.replace("admin_acc_reject_", "")
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        order = pending_orders[order_id]
        if order['status'] != 'waiting_admin_approval':
            self.bot.answer_callback_query(call.id, "⚠️ این سفارش قبلاً پردازش شده!", show_alert=True)
            return
        
        order['status'] = 'rejected'
        order['rejected_by'] = call.from_user.id
        order['rejected_at'] = time.time()
        
        updated_text = f"""❌ **سفارش رد شد**

🆔 {order_id}
👤 User ID: {order['user_id']}

رد شده توسط: {call.from_user.first_name}"""
        
        try:
            self.bot.edit_message_text(updated_text, call.message.chat.id, call.message.message_id)
        except:
            pass
        
        self.bot.send_message(
            order['user_id'],
            f"""❌ **سفارش شما رد شد**

🆔 {order_id}

دلیل: ایمیل قبلاً در OpenAI ثبت شده است.

لطفاً با یک ایمیل جدید دوباره سفارش دهید."""
        )
        
        self.bot.answer_callback_query(call.id, "❌ سفارش رد شد!", show_alert=True)
    
    def admin_deliver_order(self, call):
        """ارسال اکانت به کاربر"""
        from bot_webhook import is_admin, set_state, user_data
        if not is_admin(call.from_user.id):
            return
        
        order_id = call.data.replace("admin_acc_send_", "")
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        user_data[call.from_user.id] = {'admin_delivering_order': order_id}
        set_state(call.from_user.id, 'admin_sending_account_info')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_account_maker"))
        
        self.bot.send_message(
            call.message.chat.id,
            f"""📤 **ارسال اطلاعات اکانت**

🆔 سفارش: {order_id}

لطفاً اطلاعات کامل اکانت را ارسال کنید:

مثال:
Username: example@email.com
Password: yourpasswordhere
Link: https://chat.openai.com

text

⚠️ دقت کنید اطلاعات صحیح باشد.""",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)


# ===== MESSAGE HANDLER =====

def handle_account_maker_states(bot, db, message, user_id, state, user_data):
    """مدیریت state های Account Maker"""
    
    # ===== مرحله 1: دریافت ایمیل =====
    if state == 'chatgpt_go_waiting_email':
        email = message.text.strip()
        
        if '@' not in email or '.' not in email:
            bot.send_message(message.chat.id, "❌ لطفاً یک ایمیل معتبر وارد کنید!")
            return True
        
        order_id = user_data[user_id]['order_id']
        pending_orders[order_id]['email'] = email
        pending_orders[order_id]['status'] = 'waiting_password'
        
        from bot_webhook import set_state
        set_state(user_id, 'chatgpt_go_waiting_password')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data='account_maker'))
        
        bot.send_message(
            message.chat.id,
            f"""🔐 **مرحله 2 از 4: ارسال پسورد**

✅ ایمیل: {email}

لطفاً یک پسورد قوی برای اکانت خود وارد کنید:

⚠️ پسورد باید حداقل 8 کاراکتر باشد""",
            reply_markup=markup
        )
        return True
    
    # ===== مرحله 2: دریافت پسورد =====
    elif state == 'chatgpt_go_waiting_password':
        password = message.text.strip()
        
        if len(password) < 8:
            bot.send_message(message.chat.id, "❌ پسورد باید حداقل 8 کاراکتر باشد!")
            return True
        
        order_id = user_data[user_id]['order_id']
        pending_orders[order_id]['password'] = password
        pending_orders[order_id]['status'] = 'waiting_admin_approval'
        
        order_info = pending_orders[order_id]
        
        bot.send_message(
            message.chat.id,
            f"""✅ **مرحله 3 از 4: ثبت سفارش موفق!**

🆔 شماره سفارش: {order_id}

📧 ایمیل: {order_info['email']}
🔐 پسورد: ••••••••

💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان

⏳ سفارش شما در صف بررسی ادمین قرار گرفت.
پس از تایید، به شما اطلاع داده می‌شود."""
        )
        
        # ✅✅✅ ارسال اطلاعیه به ادمین‌ها
        send_admin_approval_request(bot, order_id)
        
        from bot_webhook import clear_state
        clear_state(user_id)
        return True
    
    # ===== مرحله 3: ادمین در حال ارسال اطلاعات =====
    elif state == 'admin_sending_account_info':
        account_info = message.text.strip()
        order_id = user_data[user_id].get('admin_delivering_order')
        
        if order_id not in pending_orders:
            bot.send_message(message.chat.id, "❌ سفارش یافت نشد!")
            from bot_webhook import clear_state
            clear_state(user_id)
            return True
        
        order = pending_orders[order_id]
        order['account_info'] = account_info
        order['status'] = 'delivered'
        order['delivered_at'] = time.time()
        
        customer_message = f"""🎉 **اکانت شما آماده است!**

🆔 سفارش: {order_id}
🎮 محصول: {CHATGPT_GO_PRODUCT['name']}

📋 **اطلاعات اکانت:**
{account_info}

⚠️ **نکات مهم:**
1. حتماً از VPN معتبر استفاده کنید
2. اطلاعات را در جای امن ذخیره کنید
3. از استفاده همزمان چند کاربر خودداری کنید

✅ این اکانت به مدت 1 سال برای شما فعال است.

🙏 از خرید شما متشکریم!"""
        
        try:
            bot.send_message(order['user_id'], customer_message)
            bot.send_message(
                message.chat.id,
                f"✅ **اکانت با موفقیت تحویل داده شد!**\n\n"
                f"🆔 سفارش: {order_id}\n"
                f"👤 کاربر: {order['user_id']}\n"
                f"📧 ایمیل: {order['email']}"
            )
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ خطا در ارسال به کاربر: {e}")
        
        from bot_webhook import clear_state
        clear_state(user_id)
        return True
    
    return False


def send_admin_approval_request(bot, order_id):
    """✅ ارسال درخواست تایید به ادمین‌ها"""
    from config import config
    
    order = pending_orders.get(order_id)
    if not order:
        logger.error(f"❌ Order {order_id} not found")
        return
    
    text = f"""🔔 **سفارش جدید ChatGPT GO**

🆔 شماره سفارش: {order_id}
👤 کاربر: @{order.get('username', 'ناشناس')} (ID: {order['user_id']})
🎮 محصول: {order['product']}

📧 ایمیل: {order['email']}
🔐 پسورد: {order['password']}

💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان
📅 زمان: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}

⏳ منتظر بررسی شما..."""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_acc_approve_{order_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"admin_acc_reject_{order_id}")
    )
    
    success_count = 0
    for admin_id in config.admin_list:
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
            success_count += 1
            logger.info(f"✅ پیام به ادمین {admin_id} ارسال شد")
        except Exception as e:
            logger.error(f"❌ خطا در ارسال به ادمین {admin_id}: {e}")
    
    if success_count > 0:
        logger.info(f"✅ درخواست {order_id} به {success_count} ادمین ارسال شد")
    else:
        logger.error("❌ هیچ ادمینی پیام دریافت نکرد!")
