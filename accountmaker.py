# accountmaker.py
"""
ماژول خرید اکانت سفارشی (Account Maker)
✅ تغییر مهم: از shared_state برای user_data/state استفاده می‌شود تا circular import حذف شود.
✅ تغییر مهم: بعد از دریافت پسورد، send_admin_approval_request صدا زده می‌شود.
"""

import logging
import time
from telebot import types
from typing import Dict, Any
from datetime import datetime

from config import config
from shared_state import user_states, user_data, pending_orders, order_counter
import shared_state
logger = logging.getLogger(__name__)

# اطلاعات محصول
CHATGPT_GO_PRODUCT = {
    "name": "🛡️ ChatGPT GO",
    "description": "اکانت ChatGPT GO — توضیحات محصول...",
    "price": 1499000,
    "delivery_time": 5
}

class AccountMakerHandlers:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def register_handlers(self):
        # ثبت callback handlers به صورت داینامیک
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

    # ===== User flows =====
    def show_account_types(self, call):
        product = CHATGPT_GO_PRODUCT
        text = f"""{product['name']}

📝 توضیحات:
{product['description']}

💰 قیمت: {product['price']:,} تومان
⏱ زمان تحویل: حداکثر {product['delivery_time']} ساعت
"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ ادامه خرید", callback_data='chatgpt_go_start_purchase'))
        markup.add(types.InlineKeyboardButton("📦 سفارشات من", callback_data='my_custom_orders'))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main'))
        try:
            self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception:
            # اگر edit ناموفق بود، پیام جدید بفرست
            self.bot.send_message(call.message.chat.id, text, reply_markup=markup)

    def start_purchase_flow(self, call):
        global order_counter
        user_id = call.from_user.id
        # ساخت order_id یکتا
        new_id = f"CGPT_{int(time.time())}_{user_id}"
        shared_state.order_counter += 1

        pending_orders[new_id] = {
            'user_id': user_id,
            'username': call.from_user.username or '',
            'status': 'waiting_email',
            'created_at': time.time(),
            'product': 'ChatGPT GO'
        }

        user_data[user_id] = {'order_id': new_id}
        user_states[user_id] = 'chatgpt_go_waiting_email'  # ✅ تغییر مهم: استفاده از shared_state

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
        # حذف پیام قبلی برای UI تمیز
        try:
            self.bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

    def show_my_orders(self, call):
        user_id = call.from_user.id
        user_orders = [(oid, o) for oid, o in pending_orders.items() if o['user_id'] == user_id]
        if not user_orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="account_maker"))
            self.bot.edit_message_text("📦 شما هنوز سفارشی ثبت نکرده‌اید.", call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        text = "📦 **سفارشات ChatGPT GO شما:**\n\n"
        for oid, o in user_orders[:10]:
            text += f"🆔 {oid}\n📧 {o.get('email','-')}\n💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان\n📊 وضعیت: {o['status']}\n\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="account_maker"))
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    # ===== Admin flows =====
    def admin_menu(self, call):
        from bot_webhook import is_admin  # import محلی تا حلقه شکسته نشود
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📋 سفارشات در انتظار", callback_data="admin_acc_pending_orders"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_menu"))
        self.bot.edit_message_text("🛡️ **مدیریت اکانت سفارشی**", call.message.chat.id, call.message.message_id, reply_markup=markup)

    def admin_pending_orders(self, call):
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            return
        orders = {oid:o for oid,o in pending_orders.items() if o['status'] in ['waiting_admin_approval','preparing']}
        if not orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
            self.bot.edit_message_text("✅ سفارشی در انتظار نیست.", call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        text = f"📋 **سفارشات در انتظار: {len(orders)} عدد**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for oid, o in list(orders.items())[:20]:
            markup.add(types.InlineKeyboardButton(f"{oid} - {o.get('email','NA')[:20]}", callback_data=f"admin_acc_order_{oid}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    def admin_show_order(self, call):
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            return
        oid = call.data.replace("admin_acc_order_", "")
        if oid not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        o = pending_orders[oid]
        text = f"""📋 **جزئیات سفارش**

🆔 شماره: {oid}
👤 کاربر: @{o.get('username','ناشناس')} (ID: {o['user_id']})
🎮 محصول: {o['product']}

📧 ایمیل: {o.get('email','-')}
🔐 پسورد: {o.get('password','-')}

💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان
📊 وضعیت: {o['status']}
📅 زمان: {time.strftime('%Y-%m-%d %H:%M', time.localtime(o['created_at']))}
"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        if o['status'] == 'waiting_admin_approval':
            markup.row(types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_acc_approve_{oid}"),
                       types.InlineKeyboardButton("❌ رد", callback_data=f"admin_acc_reject_{oid}"))
        elif o['status'] == 'preparing':
            markup.add(types.InlineKeyboardButton("📤 ارسال اکانت", callback_data=f"admin_acc_send_{oid}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_acc_pending_orders"))
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    def admin_approve_order(self, call):
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        oid = call.data.replace("admin_acc_approve_", "")
        if oid not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        o = pending_orders[oid]
        if o['status'] != 'waiting_admin_approval':
            self.bot.answer_callback_query(call.id, "⚠️ این سفارش قبلاً پردازش شده!", show_alert=True)
            return
        o['status'] = 'preparing'
        o['approved_by'] = call.from_user.id
        o['approved_at'] = time.time()
        # اطلاع به مشتری
        try:
            self.bot.send_message(o['user_id'], f"✅ سفارش {oid} توسط ادمین تایید شد. در حال آماده‌سازی اکانت...")
        except Exception as e:
            logger.error(f"خطا در ارسال پیام به کاربر: {e}")
        self.bot.answer_callback_query(call.id, "✅ سفارش تایید شد!", show_alert=True)

    def admin_reject_order(self, call):
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        oid = call.data.replace("admin_acc_reject_", "")
        if oid not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        o = pending_orders[oid]
        o['status'] = 'rejected'
        o['rejected_by'] = call.from_user.id
        o['rejected_at'] = time.time()
        try:
            self.bot.send_message(o['user_id'], f"❌ سفارش {oid} رد شد. لطفاً با ایمیل جدید دوباره تلاش کنید.")
        except Exception as e:
            logger.error(f"خطا در ارسال پیام به کاربر: {e}")
        self.bot.answer_callback_query(call.id, "❌ سفارش رد شد!", show_alert=True)

    def admin_deliver_order(self, call):
        from bot_webhook import is_admin
        if not is_admin(call.from_user.id):
            return
        oid = call.data.replace("admin_acc_send_", "")
        if oid not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        # admin آماده ارسال اطلاعات به مشتری است — جابه‌جایی state برای admin
        user_states[call.from_user.id] = 'admin_sending_account_info'
        user_data[call.from_user.id] = {'admin_delivering_order': oid}
        # درخواست اطلاعات از ادمین
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_account_maker"))
        self.bot.send_message(call.message.chat.id, f"📤 لطفاً اطلاعات اکانت برای سفارش {oid} را ارسال کنید.", reply_markup=markup)
        try:
            self.bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

# ===== مدیریت stateها (فانکشنی که bot_webhook فراخوانی می‌کند) =====
def handle_account_maker_states(bot, db, message, user_id, state, user_data_local) -> bool:
    """
    این تابع باید توسط bot_webhook فراخوانی شود.
    Returns True اگر پیام مصرف شده (یه state پردازش شد).
    """
    # مرحله 1: دریافت ایمیل
    if state == 'chatgpt_go_waiting_email':
        email = message.text.strip()
        if '@' not in email or '.' not in email:
            bot.send_message(message.chat.id, "❌ لطفاً یک ایمیل معتبر وارد کنید!")
            return True
        oid = user_data.get(user_id, {}).get('order_id')
        if not oid or oid not in pending_orders:
            bot.send_message(message.chat.id, "❌ خطا: سفارش پیدا نشد. دوباره تلاش کنید.")
            # پاکسازی state
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            return True
        pending_orders[oid]['email'] = email
        pending_orders[oid]['status'] = 'waiting_password'
        user_states[user_id] = 'chatgpt_go_waiting_password'
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data='account_maker'))
        bot.send_message(message.chat.id, f"🔐 لطفاً پسورد خود را ارسال کنید (حداقل 8 کاراکتر):", reply_markup=markup)
        return True

    # مرحله 2: دریافت پسورد
    if state == 'chatgpt_go_waiting_password':
        password = message.text.strip()
        if len(password) < 8:
            bot.send_message(message.chat.id, "❌ پسورد باید حداقل 8 کاراکتر باشد!")
            return True
        oid = user_data.get(user_id, {}).get('order_id')
        if not oid or oid not in pending_orders:
            bot.send_message(message.chat.id, "❌ خطا: سفارش پیدا نشد. دوباره تلاش کنید.")
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            return True
        pending_orders[oid]['password'] = password
        pending_orders[oid]['status'] = 'waiting_admin_approval'
        # پیام موفق به کاربر
        bot.send_message(message.chat.id, f"""✅ **سفارش ثبت شد!**
🆔 شماره سفارش: {oid}
📧 ایمیل: {pending_orders[oid]['email']}
🔐 پسورد: ••••••••
💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان
⏳ سفارش شما در صف بررسی ادمین قرار گرفت.""")
        logger.info(f"سفارش {oid} ثبت شد؛ در حال ارسال به ادمین...")
        # ✅ ارسال به ادمین (اینجا فراخوانی می‌شود — مهم)
        send_admin_approval_request(bot, oid)
        # پاکسازی state کاربر
        user_states.pop(user_id, None)
        user_data.pop(user_id, None)
        return True

    # admin در حال ارسال اطلاعات اکانت به کاربر
    if state == 'admin_sending_account_info':
        account_info = message.text.strip()
        admin_order = user_data.get(user_id, {}).get('admin_delivering_order')
        if not admin_order or admin_order not in pending_orders:
            bot.send_message(message.chat.id, "❌ سفارش یافت نشد یا منقضی شده.")
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            return True
        pending_orders[admin_order]['account_info'] = account_info
        pending_orders[admin_order]['status'] = 'delivered'
        pending_orders[admin_order]['delivered_at'] = time.time()
        # ارسال پیام به مشتری
        try:
            bot.send_message(pending_orders[admin_order]['user_id'],
                             f"🎉 اکانت شما آماده است!\n\n{account_info}")
            bot.send_message(message.chat.id, f"✅ اطلاعات به کاربر ارسال شد (سفارش {admin_order})")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ خطا در ارسال به کاربر: {e}")
        user_states.pop(user_id, None)
        user_data.pop(user_id, None)
        return True

    return False

def send_admin_approval_request(bot, order_id: str):
    """
    ارسال نوتیفیکیشن به همه ادمین‌ها با دکمه‌های تایید/رد
    ✅ تغییر مهم: استفاده از config.admin_list
    """
    logger.info(f"ارسال درخواست تایید برای سفارش {order_id}")
    order = pending_orders.get(order_id)
    if not order:
        logger.error(f"Order {order_id} not found")
        return

    text = f"""🔔 سفارش جدید ChatGPT GO

🆔 شماره سفارش: {order_id}
👤 کاربر: @{order.get('username','ناشناس')} (ID: {order['user_id']})
🎮 محصول: {order.get('product')}

📧 ایمیل: {order.get('email','-')}
🔐 پسورد: {order.get('password','-')}

💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان
📅 زمان: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}

⏳ منتظر بررسی شما...
"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_acc_approve_{order_id}"),
               types.InlineKeyboardButton("❌ رد", callback_data=f"admin_acc_reject_{order_id}"))

    success = 0
    for admin_id in config.admin_list:
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
            success += 1
            logger.info(f"پیام به ادمین {admin_id} ارسال شد")
        except Exception as e:
            logger.error(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")

    if success == 0:
        logger.error("هیچ ادمینی پیام را دریافت نکرد — بررسی کن config.ADMIN_IDS یا RAILWAY_PUBLIC_DOMAIN.")
