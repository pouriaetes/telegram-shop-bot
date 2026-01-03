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

def run_webserver():
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
    """بازگشت به منوی اصلی"""
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
    
    if product.get('requires_form'):
        form_fields = db.get_product_form_fields(product_id)
        
        if form_fields:
            user_data[user_id] = {
                'product_id': product_id,
                'product_name': product['site_name'],
                'form_fields': form_fields,
                'current_field_index': 0,
                'form_answers': {}
            }
            
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
        types.InlineKeyboardButton("💳 پرداخت مستقیم", callback_data="payment_zibal"),
        types.InlineKeyboardButton("💎 پرداخت با ارز دیجیتال", callback_data="payment_digital"),
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
        types.InlineKeyboardButton("🛡️ مدیریت اکانت سفارشی", callback_data="admin_account_maker"),
        types.InlineKeyboardButton("📦 افزودن اکانت", callback_data="admin_add_account"),
        types.InlineKeyboardButton("📊 مدیریت محصولات", callback_data="admin_manage_products"),
        types.InlineKeyboardButton("💰 افزایش موجودی کاربر", callback_data="admin_add_balance"),
        types.InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data="admin_payments"),
        types.InlineKeyboardButton("🎫 پنل پشتیبانی", callback_data="admin_support_panel"),
        types.InlineKeyboardButton("📈 آمار فروش", callback_data="admin_statistics"),
        types.InlineKeyboardButton("👤 منوی کاربر", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        "🔧 **پنل مدیریت**\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

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

# ===== MESSAGE HANDLER =====

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    """مدیریت پیام‌ها بر اساس state"""
    user_id = message.from_user.id
    state = get_state(user_id)
    
    if not state:
        return
    
    # Account Maker states
    if handle_account_maker_states(bot, db, message, user_id, state, user_data):
        return
    
    # Help states
    if handle_help_states(bot, db, message, user_id, state, user_data):
        return
    
    # Payment states
    if handle_payment_zibal_states(bot, db, message, user_id, state, user_data):
        return
    
    if handle_payment_digital_states(bot, db, message, user_id, state, user_data):
        return
    
    if handle_payment_admin_states(bot, db, message, user_id, state, user_data):
        return
    
    # فرآیند خرید با فرم
    if state.startswith("waiting_form_answer_"):
        product_id = int(state.split("_")[-1])
        data = user_data[user_id]
        
        current_index = data['current_field_index']
        current_field = data['form_fields'][current_index]
        
        # ذخیره جواب
        data['form_answers'][current_field['field_label']] = message.text
        
        # بررسی فیلد بعدی
        if current_index + 1 < len(data['form_fields']):
            data['current_field_index'] += 1
            next_field = data['form_fields'][data['current_field_index']]
            
            progress = f"({data['current_field_index'] + 1}/{len(data['form_fields'])})"
            
            bot.send_message(
                message.chat.id,
                f"📝 {progress} ❓ {next_field['field_label']}:"
            )
        else:
            # تمام سوالات پاسخ داده شد
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
    
    # افزودن محصول
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
            
            data = user_data[user_id]
            product_id = db.add_product(
                site_name=data['site_name'],
                description=data['description'],
                price=price
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_menu"))
            
            bot.send_message(
                message.chat.id,
                f"✅ محصول با موفقیت اضافه شد!\n\n"
                f"🆔 شناسه: {product_id}\n"
                f"📦 نام: {data['site_name']}\n"
                f"💰 قیمت: {price:,.0f} تومان",
                reply_markup=markup
            )
            clear_state(user_id)
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
    
    # افزودن اکانت
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
    
    # افزایش موجودی
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




# ===== اجرای ربات =====
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🤖 ربات در حال راه‌اندازی...")
    logger.info("=" * 50)
    
    try:
        bot_info = bot.get_me()
        logger.info(f"✅ ربات متصل شد: @{bot_info.username}")
        
        # حذف webhook اگر فعال باشه
        bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook حذف شد - حالت polling فعال است")
        
    except Exception as e:
        logger.error(f"❌ خطا در اتصال به تلگرام: {e}")
        exit(1)
    
    # اجرای web server برای health check
    if os.environ.get('RENDER') or os.environ.get('PORT'):
        try:
            webserver_thread = threading.Thread(target=run_webserver)
            webserver_thread.daemon = True
            webserver_thread.start()
            logger.info("🌐 Web server برای health check راه‌اندازی شد")
        except Exception as e:
            logger.warning(f"⚠️ Web server راه‌اندازی نشد: {e}")
    
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

