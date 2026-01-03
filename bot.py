import telebot
from telebot import types
import logging
from config import config
from database import Database
from accountmaker import AccountMakerHandlers, handle_account_maker_states
from help import HelpHandlers, handle_help_states
 # 👇 فقط این 3 خط را اضافه کنید
from payment_zibal import PaymentZibalHandlers, handle_payment_zibal_states
from payment_digital import PaymentDigitalHandlers, handle_payment_digital_states
from payment_admin import PaymentAdminHandlers, handle_payment_admin_states
from flask import Flask
import threading
import os

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# ایجاد Flask app برای health check
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return 'Bot is running!', 200

def run_web_server():
    """اجرای وب‌سرور در thread جداگانه"""
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ایجاد بات با timeout بالاتر
bot = telebot.TeleBot(
    config.bot_token.get_secret_value(),
    parse_mode='Markdown',
    threaded=False
)

# تنظیم پروکسی و timeout
try:
    telebot.apihelper.proxy = {'https': config.proxy_url}
    telebot.apihelper.CONNECT_TIMEOUT = 30
    telebot.apihelper.READ_TIMEOUT = 60
except:
    pass

# ایجاد دیتابیس
db = Database(config.database_path)
# ✅ اضافه کردن handlers Account Maker
account_maker_handlers = AccountMakerHandlers(bot, db)
account_maker_handlers.register_handlers()

help_handlers = HelpHandlers(bot, db)
help_handlers.register_handlers()
 # 👇 فقط این 6 خط را اضافه کنید
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
    """بررسی ادمین بودن"""
    return user_id in config.admin_list

def set_state(user_id: int, state: str):
    """تنظیم state کاربر"""
    user_states[user_id] = state

def get_state(user_id: int) -> str:
    """دریافت state کاربر"""
    return user_states.get(user_id, None)

def clear_state(user_id: int):
    """پاک کردن state کاربر"""
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_data:
        del user_data[user_id]

# ===== USER HANDLERS =====

@bot.message_handler(commands=['start'])
def cmd_start(message):
    """دستور /start"""
    clear_state(message.from_user.id)
    
    user = db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 لیست محصولات", callback_data="products_list"),
        types.InlineKeyboardButton("🎯 خرید اکانت سفارشی", callback_data="account_maker"),  # ✅ جدید
        types.InlineKeyboardButton("💳 کیف پول", callback_data="wallet"),
        types.InlineKeyboardButton("📦 سفارش‌های من", callback_data="my_orders"),
        types.InlineKeyboardButton("💬 پشتیبانی", callback_data="help_support")  # ✅ این خط را اضافه کنید

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
    """بازگشت به منوی اصلی"""
    clear_state(call.from_user.id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 لیست محصولات", callback_data="products_list"),
        types.InlineKeyboardButton("🎯 خرید اکانت سفارشی", callback_data="account_maker"),  # ✅ جدید
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

@bot.callback_query_handler(func=lambda call: call.data == "products_list")
def show_products(call):
    """نمایش لیست محصولات"""
    products = db.get_active_products()
    
    if not products:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
        
        bot.edit_message_text(
            "❌ در حال حاضر محصولی موجود نیست.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for product in products:
        stock_emoji = "✅" if product['stock_count'] > 0 else "❌"
        button_text = f"{stock_emoji} {product['site_name']} ({product['stock_count']} عدد)"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"product_{product['id']}"))
    
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    
    bot.edit_message_text(
        "🛒 لیست محصولات موجود:\n\nمحصول مورد نظر خود را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("product_"))
def show_product_detail(call):
    """نمایش جزئیات محصول"""
    product_id = int(call.data.split("_")[1])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    stock_status = "✅ موجود" if product['stock_count'] > 0 else "❌ ناموجود"
    
    text = (
        f"📦 **{product['site_name']}**\n\n"
        f"📝 توضیحات:\n{product['description']}\n\n"
        f"💰 قیمت: {product['price']:,.0f} تومان\n"
        f"📊 موجودی: {product['stock_count']} عدد\n"
        f"🔔 وضعیت: {stock_status}"
    )
    
    # بررسی نیاز به فرم
    if product.get('requires_form'):
        form_fields = db.get_product_form_fields(product_id)
        if form_fields:
            text += "\n\n📋 اطلاعات مورد نیاز برای خرید:\n"
            for field in form_fields:
                required = "⭐" if field['is_required'] else "⚪"
                text += f"{required} {field['field_label']}\n"
    
    markup = types.InlineKeyboardMarkup()
    if product['stock_count'] > 0:
        button_text = "🛒 ادامه خرید" if product.get('requires_form') else "💳 خرید"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"buy_{product_id}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="products_list"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_purchase_start(call):
    """شروع فرآیند خرید"""
    product_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    # بررسی نیاز به فرم
    if product.get('requires_form'):
        form_fields = db.get_product_form_fields(product_id)
        
        if form_fields:
            # شروع جمع‌آوری اطلاعات فرم
            user_data[user_id] = {
                'product_id': product_id,
                'product_name': product['site_name'],
                'form_fields': form_fields,
                'current_field_index': 0,
                'form_answers': {}
            }
            
            # نمایش اولین سوال
            first_field = form_fields[0]
            set_state(user_id, f"waiting_form_answer_{product_id}")
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="products_list"))
            
            bot.send_message(
                call.message.chat.id,
                f"📝 **تکمیل فرم خرید**\n\n"
                f"محصول: {product['site_name']}\n"
                f"قیمت: {product['price']:,.0f} تومان\n\n"
                f"❓ {first_field['field_label']}:",
                reply_markup=markup
            )
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
    
    # خرید بدون فرم
    process_final_purchase(user_id, product_id, call.message.chat.id, call.message.message_id, call.id)

def process_final_purchase(user_id, product_id, chat_id, message_id, callback_id=None):
    """پردازش نهایی خرید"""
    data = user_data.get(user_id, {})
    form_answers = data.get('form_answers', None)
    
    result = db.purchase_account(user_id, product_id, form_answers)
    
    if result.get("success"):
        account_info = (
            f"✅ **خرید موفق!**\n\n"
            f"🔑 **اطلاعات اکانت شما:**\n\n"
            f"👤 نام کاربری: `{result['login']}`\n"
            f"🔐 رمز عبور: `{result['password']}`\n"
        )
        
        if result.get('additional_info'):
            account_info += f"\n📋 اطلاعات تکمیلی:\n{result['additional_info']}\n"
        
        # نمایش اطلاعات فرم
        if form_answers:
            account_info += f"\n📝 **اطلاعات ارسال شده شما:**\n"
            for key, value in form_answers.items():
                account_info += f"• {key}: {value}\n"
        
        account_info += (
            f"\n💰 مبلغ پرداختی: {result['price']:,.0f} تومان\n"
            f"🆔 شماره سفارش: #{result['order_id']}\n\n"
            f"⚠️ لطفاً اطلاعات خود را در جای امن ذخیره کنید."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
        
        bot.send_message(chat_id, account_info, reply_markup=markup)
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
        
        if callback_id:
            bot.answer_callback_query(callback_id, "✅ خرید با موفقیت انجام شد!", show_alert=True)
        
        clear_state(user_id)
    else:
        error_msg = result.get('error', 'خطا در خرید')
        if callback_id:
            bot.answer_callback_query(callback_id, f"❌ {error_msg}", show_alert=True)
        else:
            bot.send_message(chat_id, f"❌ {error_msg}")

@bot.callback_query_handler(func=lambda call: call.data == "wallet")
def show_wallet(call):
    """نمایش کیف پول"""
    user_id = call.from_user.id
    clear_state(user_id)
    
    user = db.get_or_create_user(user_id, call.from_user.username)
    balance = user['balance']
    
    text = (
        f"💳 **کیف پول شما**\n\n"
        f"💰 موجودی: {balance:,} تومان\n\n"
        f"برای شارژ کیف پول، یکی از روش‌های پرداخت را انتخاب کنید:"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 پرداخت مستقیم", callback_data="payment_zibal"),  # 👈 جدید
        types.InlineKeyboardButton("💎 پرداخت با ارز دیجیتال", callback_data="payment_digital"),  # 👈 جدید
        types.InlineKeyboardButton("📜 تاریخچه تراکنش‌ها", callback_data="transactions_history"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
    )
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "my_orders")
def show_orders(call):
    """نمایش سفارشات"""
    orders = db.get_user_orders(call.from_user.id)
    
    if not orders:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
        
        bot.edit_message_text(
            "📦 شما هنوز سفارشی ثبت نکرده‌اید.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    text = "📦 **سفارش‌های شما:**\n\n"
    
    for order in orders[:10]:
        status_emoji = {"delivered": "✅", "pending": "⏳", "cancelled": "❌"}.get(order['status'], "❓")
        text += (
            f"{status_emoji} سفارش #{order['id']}\n"
            f"📦 محصول: {order['site_name']}\n"
            f"💰 مبلغ: {order['price']:,.0f} تومان\n"
            f"📅 تاریخ: {order['created_at']}\n\n"
        )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "support")
def show_support(call):
    """نمایش پشتیبانی"""
    text = (
        "📞 **پشتیبانی**\n\n"
        "برای تماس با پشتیبانی از راه‌های زیر استفاده کنید:\n\n"
        "📩 پشتیبانی تلگرام: @YourSupportBot\n"
        "📧 ایمیل: support@example.com\n\n"
        "⏰ پاسخگویی: همه روزه ۹ صبح تا ۱۲ شب"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

# ===== ADMIN HANDLERS =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_menu")
def show_admin_menu(call):
    """منوی ادمین"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    clear_state(call.from_user.id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add_product"),
        types.InlineKeyboardButton("🛡️ مدیریت اکانت سفارشی", callback_data="admin_account_maker"),  # ✅ جدید
        types.InlineKeyboardButton("📦 افزودن اکانت", callback_data="admin_add_account"),
        types.InlineKeyboardButton("📊 مدیریت محصولات", callback_data="admin_manage_products"),
        types.InlineKeyboardButton("💰 افزایش موجودی کاربر", callback_data="admin_add_balance"),
        types.InlineKeyboardButton("🎫 پنل پشتیبانی", callback_data="admin_support_panel"),  # ✅ این خط را اضافه کنید
        types.InlineKeyboardButton("📈 آمار فروش", callback_data="admin_statistics"),
        types.InlineKeyboardButton("👤 منوی کاربر", callback_data="back_to_main"),
        types.InlineKeyboardButton("💰 افزایش موجودی کاربر", callback_data="admin_add_balance"),
        types.InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data="admin_payments"),  # 👈 این خط را اضافه کنید
        types.InlineKeyboardButton("🎫 پنل پشتیبانی", callback_data="admin_support_panel")
    )
    
    bot.edit_message_text(
        "🔧 **پنل مدیریت**\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# ===== افزودن محصول =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_product")
def admin_add_product_start(call):
    """شروع افزودن محصول"""
    if not is_admin(call.from_user.id):
        return
    
    set_state(call.from_user.id, "waiting_site_name")
    user_data[call.from_user.id] = {}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_menu"))
    
    bot.send_message(
        call.message.chat.id,
        "➕ **افزودن محصول جدید**\n\n📝 نام سایت را وارد کنید:",
        reply_markup=markup
    )
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===== افزودن اکانت =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_account")
def admin_add_account_start(call):
    """شروع افزودن اکانت"""
    if not is_admin(call.from_user.id):
        return
    
    products = db.get_all_products()
    
    if not products:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
        bot.send_message(
            call.message.chat.id,
            "❌ هیچ محصولی یافت نشد. ابتدا محصول اضافه کنید.",
            reply_markup=markup
        )
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    
    products_text = "\n".join([
        f"🆔 `{p['id']}` - {p['site_name']} (موجودی: {p['stock_count']})"
        for p in products
    ])
    
    set_state(call.from_user.id, "waiting_product_id")
    user_data[call.from_user.id] = {}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_menu"))
    
    bot.send_message(
        call.message.chat.id,
        f"📦 **افزودن اکانت**\n\n"
        f"محصولات موجود:\n{products_text}\n\n"
        f"🆔 شناسه محصول را وارد کنید:",
        reply_markup=markup
    )
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===== افزایش موجودی =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_balance")
def admin_add_balance_start(call):
    """شروع افزایش موجودی"""
    if not is_admin(call.from_user.id):
        return
    
    set_state(call.from_user.id, "waiting_user_id_balance")
    user_data[call.from_user.id] = {}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_menu"))
    
    bot.send_message(
        call.message.chat.id,
        "💰 **افزایش موجودی کاربر**\n\n🆔 ID تلگرام کاربر را وارد کنید:",
        reply_markup=markup
    )
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===== مدیریت محصولات =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_products")
def admin_manage_products(call):
    """مدیریت محصولات"""
    if not is_admin(call.from_user.id):
        return
    
    products = db.get_all_products()
    
    if not products:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
        bot.edit_message_text(
            "❌ هیچ محصولی یافت نشد.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for product in products:
        status_emoji = "✅" if product['is_active'] else "❌"
        form_emoji = "📋" if product.get('requires_form') else ""
        button_text = f"{status_emoji} {form_emoji} {product['site_name']} (موجودی: {product['stock_count']})"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"admin_product_{product['id']}"))
    
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
    
    bot.edit_message_text(
        "📊 **مدیریت محصولات**\n\n📋 = دارای فرم سفارشی\n\nمحصول مورد نظر را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_product_"))
def admin_show_product_actions(call):
    """نمایش عملیات محصول"""
    product_id = int(call.data.split("_")[2])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    status = "✅ فعال" if product['is_active'] else "❌ غیرفعال"
    toggle_text = "❌ غیرفعال کردن" if product['is_active'] else "✅ فعال کردن"
    form_status = "✅ دارد" if product.get('requires_form') else "❌ ندارد"
    
    text = (
        f"📦 **{product['site_name']}**\n\n"
        f"🆔 شناسه: {product['id']}\n"
        f"📝 توضیحات: {product['description']}\n"
        f"💰 قیمت: {product['price']:,.0f} تومان\n"
        f"📊 موجودی: {product['stock_count']} عدد\n"
        f"📋 فرم سفارشی: {form_status}\n"
        f"🔔 وضعیت: {status}"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✏️ ویرایش قیمت", callback_data=f"admin_edit_price_{product_id}"),
        types.InlineKeyboardButton("📦 تغییر موجودی", callback_data=f"admin_edit_stock_{product_id}")
    )
    markup.row(
        types.InlineKeyboardButton("📋 مدیریت فرم", callback_data=f"admin_manage_form_{product_id}"),
        types.InlineKeyboardButton(toggle_text, callback_data=f"admin_toggle_{product_id}")
    )
    markup.add(types.InlineKeyboardButton("🗑 حذف محصول", callback_data=f"admin_delete_{product_id}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_products"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

# ===== مدیریت فرم محصول =====

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_manage_form_"))
def admin_manage_form(call):
    """مدیریت فرم محصول"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[3])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    form_fields = db.get_product_form_fields(product_id)
    
    text = f"📋 **مدیریت فرم محصول: {product['site_name']}**\n\n"
    
    if form_fields:
        text += "فیلدهای فعلی:\n"
        for i, field in enumerate(form_fields, 1):
            required = "⭐" if field['is_required'] else "⚪"
            text += f"{i}. {required} {field['field_label']} ({field['field_type']})\n"
    else:
        text += "❌ فرمی تعریف نشده است."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("➕ افزودن فیلد", callback_data=f"admin_add_field_{product_id}"),
        types.InlineKeyboardButton("🗑 پاک کردن فرم", callback_data=f"admin_clear_form_{product_id}")
    )
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_product_{product_id}"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_add_field_"))
def admin_add_field_start(call):
    """شروع افزودن فیلد فرم"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[3])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    set_state(call.from_user.id, "waiting_field_label")
    user_data[call.from_user.id] = {
        'product_id': product_id,
        'product_name': product['site_name']
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"admin_manage_form_{product_id}"))
    
    bot.send_message(
        call.message.chat.id,
        f"📋 **افزودن فیلد فرم**\n\n"
        f"محصول: {product['site_name']}\n\n"
        f"متن سوال را وارد کنید:\n"
        f"(مثال: ایمیل خود را وارد کنید)",
        reply_markup=markup
    )
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_clear_form_"))
def admin_clear_form_confirm(call):
    """تایید پاک کردن فرم"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[3])
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ بله، پاک شود", callback_data=f"admin_clear_form_confirm_{product_id}"),
        types.InlineKeyboardButton("❌ خیر", callback_data=f"admin_manage_form_{product_id}")
    )
    
    bot.edit_message_text(
        "⚠️ **تایید حذف**\n\nآیا مطمئن هستید که می‌خواهید تمام فیلدهای فرم را حذف کنید؟",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_clear_form_confirm_"))
def admin_clear_form_execute(call):
    """اجرای پاک کردن فرم"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[4])
    db.clear_product_form(product_id)
    
    bot.answer_callback_query(call.id, "✅ فرم با موفقیت پاک شد!", show_alert=True)
    
    # بازگشت به مدیریت فرم
    call.data = f"admin_manage_form_{product_id}"
    admin_manage_form(call)

# ===== ویرایش قیمت =====

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_edit_price_"))
def admin_edit_price_start(call):
    """شروع ویرایش قیمت"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[3])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    set_state(call.from_user.id, "waiting_new_price")
    user_data[call.from_user.id] = {'product_id': product_id, 'product_name': product['site_name']}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"admin_product_{product_id}"))
    
    bot.send_message(
        call.message.chat.id,
        f"✏️ **ویرایش قیمت**\n\n"
        f"📦 محصول: {product['site_name']}\n"
        f"💰 قیمت فعلی: {product['price']:,.0f} تومان\n\n"
        f"قیمت جدید را به تومان وارد کنید:",
        reply_markup=markup
    )
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===== ویرایش موجودی =====

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_edit_stock_"))
def admin_edit_stock_start(call):
    """شروع ویرایش موجودی"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[3])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    set_state(call.from_user.id, "waiting_new_stock")
    user_data[call.from_user.id] = {'product_id': product_id, 'product_name': product['site_name']}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"admin_product_{product_id}"))
    
    bot.send_message(
        call.message.chat.id,
        f"📦 **ویرایش موجودی**\n\n"
        f"📦 محصول: {product['site_name']}\n"
        f"📊 موجودی فعلی: {product['stock_count']} عدد\n\n"
        f"موجودی جدید را وارد کنید:",
        reply_markup=markup
    )
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_toggle_"))
def admin_toggle_product(call):
    """تغییر وضعیت محصول"""
    product_id = int(call.data.split("_")[2])
    
    db.toggle_product_status(product_id)
    bot.answer_callback_query(call.id, "✅ وضعیت محصول تغییر کرد", show_alert=True)
    
    # به‌روزرسانی نمایش
    call.data = f"admin_product_{product_id}"
    admin_show_product_actions(call)

# ===== حذف محصول =====

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_delete_") and not call.data.startswith("admin_delete_confirm_"))
def admin_delete_product_confirm(call):
    """تایید حذف محصول"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[2])
    product = db.get_product_by_id(product_id)
    
    if not product:
        bot.answer_callback_query(call.id, "❌ محصول یافت نشد!", show_alert=True)
        return
    
    text = (
        f"⚠️ **تایید حذف**\n\n"
        f"آیا مطمئن هستید که می‌خواهید این محصول را حذف کنید؟\n\n"
        f"📦 {product['site_name']}\n"
        f"📊 موجودی: {product['stock_count']} عدد\n\n"
        f"⚠️ اکانت‌های فروخته نشده نیز حذف خواهند شد!"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"admin_delete_confirm_{product_id}"),
        types.InlineKeyboardButton("❌ خیر", callback_data=f"admin_product_{product_id}")
    )
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_delete_confirm_"))
def admin_delete_product_execute(call):
    """اجرای حذف محصول"""
    if not is_admin(call.from_user.id):
        return
    
    product_id = int(call.data.split("_")[3])
    result = db.delete_product(product_id)
    
    if result.get("success"):
        bot.answer_callback_query(call.id, "✅ محصول با موفقیت حذف شد!", show_alert=True)
        admin_manage_products(call)
    else:
        bot.answer_callback_query(call.id, f"❌ {result.get('error')}", show_alert=True)

# ===== آمار فروش =====

@bot.callback_query_handler(func=lambda call: call.data == "admin_statistics")
def show_statistics(call):
    """آمار فروش"""
    if not is_admin(call.from_user.id):
        return
    
    stats = db.get_detailed_statistics()
    
    text = (
        f"📈 **آمار کامل فروشگاه**\n\n"
        f"👥 **کاربران:**\n"
        f"  • کاربران واقعی: {stats['real_users']}\n"
        f"  • ادمین‌ها: {stats['admin_count']}\n"
        f"  • مجموع: {stats['total_users']}\n\n"
        f"📦 **محصولات:**\n"
        f"  • فعال: {stats['active_products']}\n"
        f"  • غیرفعال: {stats['total_products'] - stats['active_products']}\n"
        f"  • مجموع: {stats['total_products']}\n\n"
        f"🔑 **اکانت‌ها:**\n"
        f"  • موجود: {stats['available_accounts']}\n"
        f"  • فروخته شده: {stats['sold_accounts']}\n\n"
        f"💰 **فروش:**\n"
        f"  • تعداد فروش: {stats['total_sales']}\n"
        f"  • درآمد کل: {stats['total_revenue']:,.0f} تومان"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_statistics"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

# ===== MESSAGE HANDLER برای State Management =====

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    """مدیریت پیام‌ها بر اساس state"""
    user_id = message.from_user.id
    state = get_state(user_id)
    
    if not state:
        return
    if handle_account_maker_states(bot, db, message, user_id, state, user_data):
        return
    if handle_help_states(bot, db, message, user_id, state, user_data):
        return
    # 👇 فقط این 3 بلوک را اضافه کنید

    # States پرداخت زیبال
    if handle_payment_zibal_states(bot, db, message, user_id, state, user_data):
        return

    # States پرداخت دیجیتال
    if handle_payment_digital_states(bot, db, message, user_id, state, user_data):
        return

    # States پنل ادمین پرداخت
    if handle_payment_admin_states(bot, db, message, user_id, state, user_data):
        return


    
    # ===== فرآیند خرید با فرم =====
    if state.startswith("waiting_form_answer_"):
        product_id = int(state.split("_")[-1])
        data = user_data[user_id]
        
        current_index = data['current_field_index']
        current_field = data['form_fields'][current_index]
        
        # ذخیره جواب
        data['form_answers'][current_field['field_label']] = message.text
        
        # بررسی فیلد بعدی
        if current_index + 1 < len(data['form_fields']):
            # نمایش سوال بعدی
            data['current_field_index'] += 1
            next_field = data['form_fields'][data['current_field_index']]
            
            progress = f"({data['current_field_index'] + 1}/{len(data['form_fields'])})"
            
            bot.send_message(
                message.chat.id,
                f"📝 {progress} ❓ {next_field['field_label']}:"
            )
        else:
            # تمام سوالات پاسخ داده شد - نمایش خلاصه
            summary = f"📝 **خلاصه اطلاعات شما:**\n\n"
            for key, value in data['form_answers'].items():
                summary += f"• {key}: {value}\n"
            
            product = db.get_product_by_id(product_id)
            summary += f"\n💰 مبلغ قابل پرداخت: {product['price']:,.0f} تومان"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ تایید و پرداخت", callback_data=f"confirm_purchase_{product_id}"),
                types.InlineKeyboardButton("❌ لغو", callback_data="products_list")
            )
            
            bot.send_message(message.chat.id, summary, reply_markup=markup)
            clear_state(user_id)
    
    # ===== افزودن محصول =====
    elif state == "waiting_site_name":
        user_data[user_id]['site_name'] = message.text
        set_state(user_id, "waiting_description")
        bot.send_message(message.chat.id, "📝 توضیحات محصول را وارد کنید:")
    
    elif state == "waiting_description":
        user_data[user_id]['description'] = message.text
        set_state(user_id, "waiting_price")
        bot.send_message(message.chat.id, "💰 قیمت محصول را به تومان وارد کنید:")
    
    elif state == "waiting_price":
        try:
            price = float(message.text.replace(',', ''))
            
            if price <= 0:
                bot.send_message(message.chat.id, "❌ قیمت باید بیشتر از صفر باشد!")
                return
            
            user_data[user_id]['price'] = price
            set_state(user_id, "waiting_stock")
            bot.send_message(message.chat.id, "📦 تعداد موجودی را وارد کنید (عدد):")
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
    
    elif state == "waiting_stock":
        try:
            stock = int(message.text)
            
            if stock < 0:
                bot.send_message(message.chat.id, "❌ موجودی نمی‌تواند منفی باشد!")
                return
            
            data = user_data[user_id]
            product_id = db.add_product(
                site_name=data['site_name'],
                description=data['description'],
                price=data['price'],
                stock=stock
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_menu"))
            
            bot.send_message(
                message.chat.id,
                f"✅ محصول با موفقیت اضافه شد!\n\n"
                f"🆔 شناسه: {product_id}\n"
                f"📦 نام: {data['site_name']}\n"
                f"💰 قیمت: {data['price']:,.0f} تومان\n"
                f"📊 موجودی: {stock} عدد",
                reply_markup=markup
            )
            clear_state(user_id)
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد صحیح وارد کنید!")
    
    # ===== افزودن اکانت =====
    elif state == "waiting_product_id":
        try:
            product_id = int(message.text)
            product = db.get_product_by_id(product_id)
            
            if not product:
                bot.send_message(message.chat.id, "❌ محصول با این شناسه یافت نشد!")
                return
            
            user_data[user_id]['product_id'] = product_id
            user_data[user_id]['product_name'] = product['site_name']
            set_state(user_id, "waiting_login")
            bot.send_message(
                message.chat.id,
                f"✅ محصول: {product['site_name']}\n\n👤 نام کاربری (Login) را وارد کنید:"
            )
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
    
    elif state == "waiting_login":
        user_data[user_id]['login'] = message.text
        set_state(user_id, "waiting_password")
        bot.send_message(message.chat.id, "🔐 رمز عبور (Password) را وارد کنید:")
    
    elif state == "waiting_password":
        user_data[user_id]['password'] = message.text
        set_state(user_id, "waiting_additional_info")
        bot.send_message(
            message.chat.id,
            "📋 اطلاعات تکمیلی (اختیاری) را وارد کنید\nیا /skip بزنید:"
        )
    
    elif state == "waiting_additional_info":
        additional_info = "" if message.text == "/skip" else message.text
        
        data = user_data[user_id]
        db.add_account(
            product_id=data['product_id'],
            login=data['login'],
            password=data['password'],
            additional_info=additional_info
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_menu"))
        
        bot.send_message(
            message.chat.id,
            f"✅ اکانت با موفقیت اضافه شد!\n\n"
            f"📦 محصول: {data['product_name']}\n"
            f"👤 نام کاربری: {data['login']}",
            reply_markup=markup
        )
        clear_state(user_id)
    
    # ===== افزایش موجودی کاربر =====
    elif state == "waiting_user_id_balance":
        try:
            target_user_id = int(message.text)
            user_data[user_id]['user_id'] = target_user_id
            set_state(user_id, "waiting_balance_amount")
            bot.send_message(message.chat.id, "💵 مبلغ را به تومان وارد کنید:")
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
    
    elif state == "waiting_balance_amount":
        try:
            amount = float(message.text.replace(',', ''))
            
            if amount <= 0:
                bot.send_message(message.chat.id, "❌ مبلغ باید بیشتر از صفر باشد!")
                return
            
            data = user_data[user_id]
            db.add_balance(
                user_id=data['user_id'],
                amount=amount,
                description=f"افزایش موجودی توسط ادمین {user_id}"
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_menu"))
            
            bot.send_message(
                message.chat.id,
                f"✅ موجودی کاربر {data['user_id']} به مبلغ {amount:,.0f} تومان افزایش یافت!",
                reply_markup=markup
            )
            clear_state(user_id)
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
    
    # ===== ویرایش قیمت =====
    elif state == "waiting_new_price":
        try:
            new_price = float(message.text.replace(',', ''))
            
            if new_price <= 0:
                bot.send_message(message.chat.id, "❌ قیمت باید بیشتر از صفر باشد!")
                return
            
            data = user_data[user_id]
            db.update_product(data['product_id'], price=new_price)
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به محصول", callback_data=f"admin_product_{data['product_id']}"))
            
            bot.send_message(
                message.chat.id,
                f"✅ قیمت محصول '{data['product_name']}' به {new_price:,.0f} تومان تغییر یافت!",
                reply_markup=markup
            )
            clear_state(user_id)
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
    
    # ===== ویرایش موجودی =====
    elif state == "waiting_new_stock":
        try:
            new_stock = int(message.text)
            
            if new_stock < 0:
                bot.send_message(message.chat.id, "❌ موجودی نمی‌تواند منفی باشد!")
                return
            
            data = user_data[user_id]
            db.update_product_stock(data['product_id'], new_stock)
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به محصول", callback_data=f"admin_product_{data['product_id']}"))
            
            bot.send_message(
                message.chat.id,
                f"✅ موجودی محصول '{data['product_name']}' به {new_stock} عدد تغییر یافت!",
                reply_markup=markup
            )
            clear_state(user_id)
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد صحیح وارد کنید!")
    
    # ===== افزودن فیلد فرم =====
    elif state == "waiting_field_label":
        data = user_data[user_id]
        data['field_label'] = message.text
        
        # برای سادگی، همه فیلدها text و required هستند
        # می‌توانید بعداً انتخاب نوع فیلد را اضافه کنید
        
        field_order = len(db.get_product_form_fields(data['product_id']))
        
        db.add_form_field(
            product_id=data['product_id'],
            field_name=f"field_{field_order + 1}",
            field_label=data['field_label'],
            field_type='text',
            is_required=True,
            field_order=field_order
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت فرم", callback_data=f"admin_manage_form_{data['product_id']}"))
        
        bot.send_message(
            message.chat.id,
            f"✅ فیلد با موفقیت اضافه شد!\n\n"
            f"📦 محصول: {data['product_name']}\n"
            f"❓ سوال: {data['field_label']}",
            reply_markup=markup
        )
        clear_state(user_id)
# ===== Handler برای تمام پیام‌های متنی =====
@bot.message_handler(func=lambda message: True)
def message_router(message):
    """مدیریت پیام‌های متنی بر اساس وضعیت (State) کاربر"""
    user_id = message.from_user.id
    state = get_state(user_id)
    
    if not state:
        return
    
    # مدیریت Account Maker states
    if handle_account_maker_states(bot, db, message, user_id, state, user_data):
        return
    
    # مدیریت Help states
    if handle_help_states(bot, db, message, user_id, state, user_data):
        return
    
    # مدیریت Payment Zibal states
    if handle_payment_zibal_states(bot, db, message, user_id, state, user_data):
        return
    
    # مدیریت Payment Digital states
    if handle_payment_digital_states(bot, db, message, user_id, state, user_data):
        return
    
    # مدیریت Payment Admin states
    if handle_payment_admin_states(bot, db, message, user_id, state, user_data):
        return
    
    # مدیریت افزودن محصول
    if state == "waiting_site_name":
        try:
            site_name = message.text.strip()
            if not site_name:
                bot.send_message(message.chat.id, "❌ نام سایت نمی‌تواند خالی باشد!")
                return
            
            user_data[user_id] = {'site_name': site_name}
            set_state(user_id, "waiting_description")
            bot.send_message(message.chat.id, "📝 توضیحات محصول را وارد کنید:")
        except Exception as e:
            logger.error(f"Error in waiting_site_name: {e}")
            bot.send_message(message.chat.id, "❌ خطا در ثبت نام سایت!")
        return
    
    elif state == "waiting_description":
        try:
            data = user_data[user_id]
            data['description'] = message.text.strip()
            set_state(user_id, "waiting_price")
            bot.send_message(message.chat.id, "💰 قیمت محصول را به تومان وارد کنید:")
        except Exception as e:
            logger.error(f"Error in waiting_description: {e}")
            bot.send_message(message.chat.id, "❌ خطا در ثبت توضیحات!")
        return
    
    elif state == "waiting_price":
        try:
            price = float(message.text.strip())
            if price <= 0:
                bot.send_message(message.chat.id, "❌ قیمت باید بیشتر از صفر باشد!")
                return
            
            data = user_data[user_id]
            product_id = db.add_product(
                site_name=data['site_name'],
                description=data['description'],
                price=price
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("➕ افزودن اکانت", callback_data=f"admin_add_account_{product_id}"))
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_products"))
            
            bot.send_message(
                message.chat.id,
                f"✅ محصول با موفقیت اضافه شد!\n\n"
                f"🌐 سایت: {data['site_name']}\n"
                f"💰 قیمت: {price:,.0f} تومان\n\n"
                f"حالا می‌توانید اکانت اضافه کنید:",
                reply_markup=markup
            )
            clear_state(user_id)
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
        except Exception as e:
            logger.error(f"Error in waiting_price: {e}")
            bot.send_message(message.chat.id, "❌ خطا در ثبت قیمت!")
        return
    
    # مدیریت افزودن اکانت
    elif state == "waiting_login":
        try:
            data = user_data[user_id]
            data['login'] = message.text.strip()
            set_state(user_id, "waiting_password")
            bot.send_message(message.chat.id, "🔑 رمز عبور اکانت را وارد کنید:")
        except Exception as e:
            logger.error(f"Error in waiting_login: {e}")
            bot.send_message(message.chat.id, "❌ خطا!")
        return
    
    elif state == "waiting_password":
        try:
            data = user_data[user_id]
            data['password'] = message.text.strip()
            set_state(user_id, "waiting_additional_info")
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("بدون اطلاعات اضافی")
            
            bot.send_message(
                message.chat.id,
                "📋 اطلاعات اضافی (اختیاری):\n"
                "مثلاً: ایمیل بازیابی، سوال امنیتی و ...\n\n"
                "یا دکمه 'بدون اطلاعات اضافی' را بزنید:",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error in waiting_password: {e}")
            bot.send_message(message.chat.id, "❌ خطا!")
        return
    
    elif state == "waiting_additional_info":
        try:
            data = user_data[user_id]
            additional_info = None if message.text == "بدون اطلاعات اضافی" else message.text.strip()
            
            db.add_account(
                product_id=data['product_id'],
                login=data['login'],
                password=data['password'],
                additional_info=additional_info
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("➕ افزودن اکانت دیگر", callback_data=f"admin_add_account_{data['product_id']}"))
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به محصول", callback_data=f"admin_product_{data['product_id']}"))
            
            bot.send_message(
                message.chat.id,
                "✅ اکانت با موفقیت اضافه شد!",
                reply_markup=markup
            )
            clear_state(user_id)
        except Exception as e:
            logger.error(f"Error in waiting_additional_info: {e}")
            bot.send_message(message.chat.id, "❌ خطا در افزودن اکانت!")
        return
    
    # مدیریت ویرایش قیمت
    elif state == "waiting_new_price":
        try:
            new_price = float(message.text)
            if new_price <= 0:
                bot.send_message(message.chat.id, "❌ قیمت باید بیشتر از صفر باشد!")
                return
            
            data = user_data[user_id]
            db.update_product_price(data['product_id'], new_price)
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به محصول", callback_data=f"admin_product_{data['product_id']}"))
            
            bot.send_message(
                message.chat.id,
                f"✅ قیمت محصول '{data['product_name']}' به {new_price:,.0f} تومان تغییر یافت!",
                reply_markup=markup
            )
            clear_state(user_id)
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
        return
    
    # مدیریت ویرایش موجودی
    elif state == "waiting_new_stock":
        try:
            new_stock = int(message.text)
            if new_stock < 0:
                bot.send_message(message.chat.id, "❌ موجودی نمی‌تواند منفی باشد!")
                return
            
            data = user_data[user_id]
            db.update_product_stock(data['product_id'], new_stock)
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به محصول", callback_data=f"admin_product_{data['product_id']}"))
            
            bot.send_message(
                message.chat.id,
                f"✅ موجودی محصول '{data['product_name']}' به {new_stock} عدد تغییر یافت!",
                reply_markup=markup
            )
            clear_state(user_id)
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد صحیح وارد کنید!")
        return
    
    # مدیریت افزودن فیلد فرم
    elif state == "waiting_field_label":
        try:
            data = user_data[user_id]
            data['field_label'] = message.text
            
            field_order = len(db.get_product_form_fields(data['product_id']))
            
            db.add_form_field(
                product_id=data['product_id'],
                field_name=f"field_{field_order + 1}",
                field_label=data['field_label'],
                field_type='text',
                is_required=True,
                field_order=field_order
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت فرم", callback_data=f"admin_manage_form_{data['product_id']}"))
            
            bot.send_message(
                message.chat.id,
                f"✅ فیلد با موفقیت اضافه شد!\n\n"
                f"📦 محصول: {data['product_name']}\n"
                f"❓ سوال: {data['field_label']}",
                reply_markup=markup
            )
            clear_state(user_id)
        except Exception as e:
            logger.error(f"Error in waiting_field_label: {e}")
            bot.send_message(message.chat.id, "❌ خطا!")
        return

# ===== تایید نهایی خرید با فرم =====

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_purchase_"))
def confirm_purchase_with_form(call):
    """تایید و پرداخت نهایی"""
    product_id = int(call.data.split("_")[2])
    user_id = call.from_user.id
    
    process_final_purchase(user_id, product_id, call.message.chat.id, call.message.message_id, call.id)
@bot.message_handler(func=lambda message: True)
def message_router(message):
    """مدیریت پیام‌های متنی بر اساس وضعیت (State) کاربر"""
    user_id = message.from_user.id
    state = get_state(user_id)
    
    if not state:
        return

    # مدیریت پرداخت زیبال (مبلغ دلخواه)
    if state == "payment_zibal_waiting_amount":
        handle_payment_zibal_states(bot, db, message, user_id, state, user_data)
        return

    # مدیریت فرم‌های خرید (اگر دارید)
    if state.startswith("waiting_form_answer_"):
        # اگر هندلر مربوط به فرم در فایل دیگری است آن را صدا بزنید
        # account_maker_handlers.handle_state(...) 
        pass
# ===== اجرای ربات =====
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🤖 ربات در حال راه‌اندازی...")
    logger.info("=" * 50)
    
    # بررسی اتصال به تلگرام
    try:
        bot_info = bot.get_me()
        logger.info(f"✅ ربات متصل شد: @{bot_info.username}")
    except Exception as e:
        logger.error(f"❌ خطا در اتصال به تلگرام: {e}")
        exit(1)
    
    # اجرای web server برای health check (برای Render)
    if os.environ.get('RENDER') or os.environ.get('PORT'):
        try:
            webserver_thread = threading.Thread(target=run_webserver)
            webserver_thread.daemon = True
            webserver_thread.start()
            logger.info("🌐 Web server برای health check راه‌اندازی شد")
        except Exception as e:
            logger.warning(f"⚠️ Web server راه‌اندازی نشد: {e}")
    
    # اجرای ربات
    logger.info("🚀 ربات آماده دریافت پیام است!")
    logger.info("=" * 50)
    
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            skip_pending=True
        )
    except KeyboardInterrupt:
        logger.info("⏹ ربات توسط کاربر متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()






