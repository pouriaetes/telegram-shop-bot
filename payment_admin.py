"""
پنل ادمین برای مدیریت سیستم پرداخت
- تنظیمات درگاه زیبال
- تنظیمات NOWPayments
- مدیریت تراکنش‌ها
- آمار و گزارش‌ها
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from telebot import types

logger = logging.getLogger(__name__)

# Import database classes
from payment_zibal import PaymentZibalDB, ZibalAPI
from payment_digital import PaymentDigitalDB, NOWPaymentsAPI

# ===== HANDLERS =====

class PaymentAdminHandlers:
    """handlers پنل ادمین پرداخت"""
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    def register_handlers(self):
        """ثبت handlers"""
        
        # Menu handlers
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_payments")(self.main_menu)
        
        # Zibal handlers
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_payment_zibal_settings")(self.zibal_settings)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_zibal_toggle")(self.zibal_toggle)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_zibal_set_merchant")(self.zibal_set_merchant)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_zibal_set_callback")(self.zibal_set_callback)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_zibal_set_limits")(self.zibal_set_limits)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_zibal_transactions")(self.zibal_transactions)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_zibal_tx_"))(self.zibal_transaction_detail)
        
        # Crypto handlers
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_payment_crypto_settings")(self.crypto_settings)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_crypto_toggle")(self.crypto_toggle)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_crypto_set_api")(self.crypto_set_api)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_crypto_set_callback")(self.crypto_set_callback)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_crypto_test_api")(self.crypto_test_api)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_crypto_transactions")(self.crypto_transactions)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_crypto_tx_"))(self.crypto_transaction_detail)
        
        # Statistics
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_payment_statistics")(self.payment_statistics)
        
        # Manual verification
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_verify_zibal_"))(self.manual_verify_zibal)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_verify_crypto_"))(self.manual_verify_crypto)
    
    # ===== MAIN MENU =====
    
    def main_menu(self, call):
        """منوی اصلی پنل پرداخت"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        with self.db.get_connection() as conn:
            zibal_stats = PaymentZibalDB.get_statistics(conn)
            crypto_stats = PaymentDigitalDB.get_statistics(conn)
            
            zibal_settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
            crypto_settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        zibal_status = "✅ فعال" if zibal_settings and zibal_settings.get('is_active') else "❌ غیرفعال"
        crypto_status = "✅ فعال" if crypto_settings and crypto_settings.get('is_active') else "❌ غیرفعال"
        
        text = (
            f"💳 **پنل مدیریت پرداخت‌ها**\n\n"
            f"**درگاه زیبال:** {zibal_status}\n"
            f"├ تراکنش‌های موفق: {zibal_stats['successful_count']}\n"
            f"├ مبلغ کل: {zibal_stats['total_amount']:,.0f} تومان\n"
            f"└ در انتظار: {zibal_stats['pending_count']}\n\n"
            f"**ارز دیجیتال:** {crypto_status}\n"
            f"├ تراکنش‌های موفق: {crypto_stats['successful_count']}\n"
            f"├ مبلغ کل: ${crypto_stats['total_amount_usd']:,.2f}\n"
            f"└ در انتظار: {crypto_stats['pending_count']}"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💳 تنظیمات زیبال", callback_data="admin_payment_zibal_settings"),
            types.InlineKeyboardButton("💎 تنظیمات ارز دیجیتال", callback_data="admin_payment_crypto_settings"),
            types.InlineKeyboardButton("📊 آمار کامل", callback_data="admin_payment_statistics"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    # ===== ZIBAL SETTINGS =====
    
    def zibal_settings(self, call):
        """تنظیمات زیبال"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
        
        if not settings:
            # ایجاد تنظیمات اولیه
            with self.db.get_connection() as conn:
                PaymentZibalDB.update_payment_settings(
                    conn, 'zibal',
                    is_active=0,
                    merchant_id='',
                    callback_url='',
                    min_amount=10000,
                    max_amount=50000000
                )
                settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
        
        status = "✅ فعال" if settings.get('is_active') else "❌ غیرفعال"
        merchant = settings.get('merchant_id') or "تنظیم نشده"
        callback = settings.get('callback_url') or "تنظیم نشده"
        min_amount = settings.get('min_amount', 10000)
        max_amount = settings.get('max_amount', 50000000)
        
        text = (
            f"💳 **تنظیمات درگاه زیبال**\n\n"
            f"📊 وضعیت: {status}\n"
            f"🔑 Merchant: `{merchant}`\n"
            f"🔗 Callback URL: `{callback}`\n"
            f"💰 حداقل: {min_amount:,} تومان\n"
            f"💰 حداکثر: {max_amount:,} تومان"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        toggle_text = "❌ غیرفعال کردن" if settings.get('is_active') else "✅ فعال کردن"
        markup.add(
            types.InlineKeyboardButton(toggle_text, callback_data="admin_zibal_toggle"),
            types.InlineKeyboardButton("🔑 تنظیم Merchant ID", callback_data="admin_zibal_set_merchant"),
            types.InlineKeyboardButton("🔗 تنظیم Callback URL", callback_data="admin_zibal_set_callback"),
            types.InlineKeyboardButton("💰 تنظیم محدودیت مبلغ", callback_data="admin_zibal_set_limits"),
            types.InlineKeyboardButton("📜 تراکنش‌ها", callback_data="admin_zibal_transactions"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payments")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def zibal_toggle(self, call):
        """فعال/غیرفعال کردن زیبال"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
            new_status = 0 if settings.get('is_active') else 1
            
            PaymentZibalDB.update_payment_settings(conn, 'zibal', is_active=new_status)
        
        status_text = "فعال" if new_status else "غیرفعال"
        self.bot.answer_callback_query(call.id, f"✅ درگاه زیبال {status_text} شد!", show_alert=True)
        
        # بازگشت به منو
        self.zibal_settings(call)
    
    def zibal_set_merchant(self, call):
        """تنظیم merchant ID"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = call.from_user.id
        set_state(user_id, "payment_admin_zibal_merchant")
        user_data[user_id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_payment_zibal_settings"))
        
        self.bot.send_message(
            call.message.chat.id,
            "🔑 **تنظیم Merchant ID**\n\n"
            "Merchant ID خود را از پنل زیبال وارد کنید:\n\n"
            "مثال: `zibal`",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def zibal_set_callback(self, call):
        """تنظیم callback URL"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = call.from_user.id
        set_state(user_id, "payment_admin_zibal_callback")
        user_data[user_id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_payment_zibal_settings"))
        
        self.bot.send_message(
            call.message.chat.id,
            "🔗 **تنظیم Callback URL**\n\n"
            "آدرس Callback URL خود را وارد کنید:\n\n"
            "مثال: `https://yourdomain.com/zibal/callback`\n\n"
            "⚠️ این آدرس باید به سرور webhook شما متصل باشد.",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def zibal_set_limits(self, call):
        """تنظیم محدودیت‌ها"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = call.from_user.id
        set_state(user_id, "payment_admin_zibal_limits")
        user_data[user_id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_payment_zibal_settings"))
        
        self.bot.send_message(
            call.message.chat.id,
            "💰 **تنظیم محدودیت مبلغ**\n\n"
            "حداقل و حداکثر مبلغ را وارد کنید (به تومان):\n\n"
            "فرمت: `حداقل,حداکثر`\n\n"
            "مثال: `10000,50000000`",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def zibal_transactions(self, call):
        """لیست تراکنش‌های زیبال"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM zibal_transactions
                ORDER BY created_at DESC
                LIMIT 20
            """)
            transactions = [dict(row) for row in cursor.fetchall()]
        
        if not transactions:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payment_zibal_settings"))
            
            self.bot.edit_message_text(
                "📭 تراکنشی یافت نشد.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "📜 **تراکنش‌های زیبال (20 تای آخر):**\n\n"
        
        status_emoji = {
            'pending': '⏳',
            'awaiting_payment': '💳',
            'success': '✅',
            'failed': '❌',
            'canceled': '🚫'
        }
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for tx in transactions[:10]:
            emoji = status_emoji.get(tx['status'], '❓')
            button_text = f"{emoji} {tx['user_id']} - {tx['amount']:,}T - {tx['status']}"
            markup.add(
                types.InlineKeyboardButton(button_text, callback_data=f"admin_zibal_tx_{tx['id']}")
            )
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payment_zibal_settings"))
        
        self.bot.edit_message_text(
            text + "👇 برای مشاهده جزئیات، روی هر تراکنش کلیک کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    def zibal_transaction_detail(self, call):
        """جزئیات تراکنش زیبال"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        tx_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            transaction = PaymentZibalDB.get_transaction(conn, transaction_id=tx_id)
        
        if not transaction:
            self.bot.answer_callback_query(call.id, "❌ تراکنش یافت نشد!", show_alert=True)
            return
        
        status_text = {
            'pending': '⏳ در انتظار',
            'awaiting_payment': '💳 منتظر پرداخت',
            'success': '✅ موفق',
            'failed': '❌ ناموفق',
            'canceled': '🚫 لغو شده'
        }
        
        text = (
            f"📄 **جزئیات تراکنش زیبال**\n\n"
            f"🆔 شناسه: `{transaction['id']}`\n"
            f"👤 کاربر: `{transaction['user_id']}`\n"
            f"💰 مبلغ: {transaction['amount']:,} تومان\n"
            f"📊 وضعیت: {status_text.get(transaction['status'], transaction['status'])}\n"
            f"🔢 Track ID: `{transaction['track_id'] or 'ندارد'}`\n"
            f"🔢 شماره پیگیری: `{transaction['reference_number'] or 'ندارد'}`\n"
            f"💳 شماره کارت: `{transaction['card_number'] or 'ندارد'}`\n"
            f"📅 تاریخ ایجاد: {transaction['created_at']}\n"
            f"✅ تاریخ پرداخت: {transaction['paid_at'] or 'ندارد'}\n"
            f"📝 توضیحات: {transaction['description'] or 'ندارد'}"
        )
        
        markup = types.InlineKeyboardMarkup()
        
        if transaction['status'] in ['awaiting_payment', 'pending'] and transaction['track_id']:
            markup.add(
                types.InlineKeyboardButton("🔄 تایید دستی", callback_data=f"admin_verify_zibal_{tx_id}")
            )
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_zibal_transactions"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def manual_verify_zibal(self, call):
        """تایید دستی تراکنش زیبال"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        tx_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            transaction = PaymentZibalDB.get_transaction(conn, transaction_id=tx_id)
            
            if not transaction:
                self.bot.answer_callback_query(call.id, "❌ تراکنش یافت نشد!", show_alert=True)
                return
            
            settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
        
        # تایید از زیبال
        from payment_zibal import PaymentZibalHandlers
        handlers = PaymentZibalHandlers(self.bot, self.db)
        result = handlers.verify_payment_manual(transaction['user_id'], transaction['track_id'])
        
        if result['success']:
            self.bot.answer_callback_query(
                call.id,
                f"✅ پرداخت تایید شد!\nمبلغ: {result['amount']:,} تومان",
                show_alert=True
            )
            
            # بازگشت به لیست
            call.data = "admin_zibal_transactions"
            self.zibal_transactions(call)
        else:
            self.bot.answer_callback_query(
                call.id,
                f"❌ {result.get('error')}",
                show_alert=True
            )
    
    # ===== CRYPTO SETTINGS =====
    
    def crypto_settings(self, call):
        """تنظیمات ارز دیجیتال"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        if not settings:
            # ایجاد تنظیمات اولیه
            with self.db.get_connection() as conn:
                PaymentZibalDB.update_payment_settings(
                    conn, 'crypto',
                    is_active=0,
                    api_key='',
                    callback_url=''
                )
                settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        status = "✅ فعال" if settings.get('is_active') else "❌ غیرفعال"
        api_key = settings.get('api_key') or "تنظیم نشده"
        api_display = api_key[:20] + "..." if len(api_key) > 20 else api_key
        callback = settings.get('callback_url') or "تنظیم نشده"
        
        text = (
            f"💎 **تنظیمات پرداخت ارز دیجیتال**\n\n"
            f"📊 وضعیت: {status}\n"
            f"🔑 API Key: `{api_display}`\n"
            f"🔗 Callback URL: `{callback}`\n\n"
            f"ارزهای پشتیبانی شده:\n"
            f"₿ Bitcoin (BTC)\n"
            f"Ξ Ethereum (ETH)\n"
            f"₮ Tether (USDT)\n"
            f"🔺 Tron (TRX)"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        toggle_text = "❌ غیرفعال کردن" if settings.get('is_active') else "✅ فعال کردن"
        markup.add(
            types.InlineKeyboardButton(toggle_text, callback_data="admin_crypto_toggle"),
            types.InlineKeyboardButton("🔑 تنظیم API Key", callback_data="admin_crypto_set_api"),
            types.InlineKeyboardButton("🔗 تنظیم Callback URL", callback_data="admin_crypto_set_callback"),
            types.InlineKeyboardButton("🧪 تست API", callback_data="admin_crypto_test_api"),
            types.InlineKeyboardButton("📜 تراکنش‌ها", callback_data="admin_crypto_transactions"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payments")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def crypto_toggle(self, call):
        """فعال/غیرفعال کردن کریپتو"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
            new_status = 0 if settings.get('is_active') else 1
            
            PaymentZibalDB.update_payment_settings(conn, 'crypto', is_active=new_status)
        
        status_text = "فعال" if new_status else "غیرفعال"
        self.bot.answer_callback_query(call.id, f"✅ پرداخت ارز دیجیتال {status_text} شد!", show_alert=True)
        
        # بازگشت به منو
        self.crypto_settings(call)
    
    def crypto_set_api(self, call):
        """تنظیم API key"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = call.from_user.id
        set_state(user_id, "payment_admin_crypto_api")
        user_data[user_id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_payment_crypto_settings"))
        
        self.bot.send_message(
            call.message.chat.id,
            "🔑 **تنظیم NOWPayments API Key**\n\n"
            "API Key خود را از پنل NOWPayments وارد کنید:\n\n"
            "🔗 https://nowpayments.io/\n\n"
            "⚠️ این کلید محرمانه است!",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def crypto_set_callback(self, call):
        """تنظیم callback URL"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = call.from_user.id
        set_state(user_id, "payment_admin_crypto_callback")
        user_data[user_id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_payment_crypto_settings"))
        
        self.bot.send_message(
            call.message.chat.id,
            "🔗 **تنظیم IPN Callback URL**\n\n"
            "آدرس IPN Callback URL خود را وارد کنید:\n\n"
            "مثال: `https://yourdomain.com/nowpayments/ipn`\n\n"
            "⚠️ این آدرس باید به سرور webhook شما متصل باشد.",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def crypto_test_api(self, call):
        """تست API"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        if not settings or not settings.get('api_key'):
            self.bot.answer_callback_query(call.id, "❌ API Key تنظیم نشده!", show_alert=True)
            return
        
        # تست API
        nowpayments = NOWPaymentsAPI(settings['api_key'])
        currencies = nowpayments.get_available_currencies()
        
        if currencies and len(currencies) > 0:
            self.bot.answer_callback_query(
                call.id,
                f"✅ API کار می‌کند!\n{len(currencies)} ارز در دسترس است.",
                show_alert=True
            )
        else:
            self.bot.answer_callback_query(
                call.id,
                "❌ خطا در اتصال به API!\nلطفاً API Key را بررسی کنید.",
                show_alert=True
            )
    
    def crypto_transactions(self, call):
        """لیست تراکنش‌های کریپتو"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM crypto_transactions
                ORDER BY created_at DESC
                LIMIT 20
            """)
            transactions = [dict(row) for row in cursor.fetchall()]
        
        if not transactions:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payment_crypto_settings"))
            
            self.bot.edit_message_text(
                "📭 تراکنشی یافت نشد.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "📜 **تراکنش‌های ارز دیجیتال (20 تای آخر):**\n\n"
        
        status_emoji = {
            'waiting': '⏳',
            'confirming': '🔄',
            'sending': '📤',
            'finished': '✅',
            'failed': '❌',
            'expired': '⏰'
        }
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for tx in transactions[:10]:
            emoji = status_emoji.get(tx['payment_status'], '❓')
            button_text = f"{emoji} {tx['user_id']} - ${tx['amount_usd']:.2f} - {tx['currency'].upper()}"
            markup.add(
                types.InlineKeyboardButton(button_text, callback_data=f"admin_crypto_tx_{tx['id']}")
            )
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payment_crypto_settings"))
        
        self.bot.edit_message_text(
            text + "👇 برای مشاهده جزئیات، روی هر تراکنش کلیک کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    def crypto_transaction_detail(self, call):
        """جزئیات تراکنش کریپتو"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        tx_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            transaction = PaymentDigitalDB.get_transaction(conn, transaction_id=tx_id)
        
        if not transaction:
            self.bot.answer_callback_query(call.id, "❌ تراکنش یافت نشد!", show_alert=True)
            return
        
        status_text = {
            'waiting': '⏳ در انتظار پرداخت',
            'confirming': '🔄 در حال تایید',
            'sending': '📤 در حال ارسال',
            'finished': '✅ موفق',
            'failed': '❌ ناموفق',
            'expired': '⏰ منقضی شده'
        }
        
        text = (
            f"📄 **جزئیات تراکنش ارز دیجیتال**\n\n"
            f"🆔 شناسه: `{transaction['id']}`\n"
            f"👤 کاربر: `{transaction['user_id']}`\n"
            f"💰 مبلغ: ${transaction['amount_usd']:.2f}\n"
            f"🪙 ارز: {transaction['currency'].upper()}\n"
            f"📊 وضعیت: {status_text.get(transaction['payment_status'], transaction['payment_status'])}\n"
            f"🔢 Payment ID: `{transaction['payment_id'] or 'ندارد'}`\n"
            f"🔢 Order ID: `{transaction['order_id']}`\n"
            f"📍 آدرس: `{transaction['pay_address'] or 'ندارد'}`\n"
            f"💵 مبلغ پرداختی: {transaction['pay_amount'] or 'ندارد'} {transaction['currency'].upper()}\n"
            f"✅ واقعاً پرداخت شده: {transaction['actual_amount_crypto'] or 'ندارد'}\n"
            f"📅 تاریخ ایجاد: {transaction['created_at']}\n"
            f"✅ تاریخ تکمیل: {transaction['finished_at'] or 'ندارد'}\n"
            f"📝 توضیحات: {transaction['description'] or 'ندارد'}"
        )
        
        markup = types.InlineKeyboardMarkup()
        
        if transaction['payment_status'] in ['waiting', 'confirming'] and transaction['payment_id']:
            markup.add(
                types.InlineKeyboardButton("🔄 بروزرسانی وضعیت", callback_data=f"admin_verify_crypto_{tx_id}")
            )
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_transactions"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def manual_verify_crypto(self, call):
        """بروزرسانی وضعیت تراکنش کریپتو"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        tx_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            transaction = PaymentDigitalDB.get_transaction(conn, transaction_id=tx_id)
            
            if not transaction:
                self.bot.answer_callback_query(call.id, "❌ تراکنش یافت نشد!", show_alert=True)
                return
            
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        # بروزرسانی از NOWPayments
        nowpayments = NOWPaymentsAPI(settings['api_key'])
        status_result = nowpayments.get_payment_status(transaction['payment_id'])
        
        if status_result['success']:
            new_status = status_result['payment_status']
            
            with self.db.get_connection() as conn:
                PaymentDigitalDB.update_transaction(
                    conn,
                    tx_id,
                    payment_status=new_status,
                    actual_amount_crypto=status_result.get('actually_paid'),
                    actual_amount_usd=status_result.get('outcome_amount')
                )
                
                # اگر تکمیل شد
                if new_status == 'finished':
                    from payment_digital import PaymentDigitalHandlers
                    handlers = PaymentDigitalHandlers(self.bot, self.db)
                    
                    amount_toman = int(transaction['amount_usd'] * handlers.USD_TO_TOMAN_RATE)
                    
                    conn.execute(
                        "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                        (amount_toman, transaction['user_id'])
                    )
                    
                    conn.execute("""
                        INSERT INTO transactions (user_id, amount, type, description)
                        VALUES (?, ?, 'deposit', ?)
                    """, (transaction['user_id'], amount_toman, f"شارژ کیف پول - کریپتو"))
            
            self.bot.answer_callback_query(
                call.id,
                f"✅ وضعیت به‌روزرسانی شد!\nوضعیت جدید: {new_status}",
                show_alert=True
            )
            
            # بازگشت به جزئیات
            call.data = f"admin_crypto_tx_{tx_id}"
            self.crypto_transaction_detail(call)
        else:
            self.bot.answer_callback_query(
                call.id,
                f"❌ {status_result.get('error')}",
                show_alert=True
            )
    
    # ===== STATISTICS =====
    
    def payment_statistics(self, call):
        """آمار کامل پرداخت‌ها"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            zibal_stats = PaymentZibalDB.get_statistics(conn)
            crypto_stats = PaymentDigitalDB.get_statistics(conn)
            
            # آمار 30 روز اخیر - زیبال
            cursor = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(amount), 0)
                FROM zibal_transactions
                WHERE status = 'success' 
                AND datetime(created_at) > datetime('now', '-30 days')
            """)
            zibal_30d = cursor.fetchone()
            
            # آمار 30 روز اخیر - کریپتو
            cursor = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(actual_amount_usd), 0)
                FROM crypto_transactions
                WHERE payment_status = 'finished'
                AND datetime(created_at) > datetime('now', '-30 days')
            """)
            crypto_30d = cursor.fetchone()
        
        text = (
            f"📊 **آمار کامل پرداخت‌ها**\n\n"
            f"**💳 درگاه زیبال:**\n"
            f"├ کل تراکنش‌های موفق: {zibal_stats['successful_count']}\n"
            f"├ مجموع درآمد: {zibal_stats['total_amount']:,.0f} تومان\n"
            f"├ در انتظار: {zibal_stats['pending_count']}\n"
            f"└ 30 روز اخیر: {zibal_30d[0]} تراکنش - {zibal_30d[1]:,.0f} تومان\n\n"
            f"**💎 ارز دیجیتال:**\n"
            f"├ کل تراکنش‌های موفق: {crypto_stats['successful_count']}\n"
            f"├ مجموع درآمد: ${crypto_stats['total_amount_usd']:,.2f}\n"
            f"├ در انتظار: {crypto_stats['pending_count']}\n"
            f"└ 30 روز اخیر: {crypto_30d[0]} تراکنش - ${crypto_30d[1]:,.2f}\n\n"
            f"**📈 جمع کل:**\n"
            f"└ {zibal_stats['successful_count'] + crypto_stats['successful_count']} تراکنش موفق"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payments"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)


# ===== MESSAGE HANDLERS برای State Management =====

def handle_payment_admin_states(bot, db, message, user_id, state, user_data):
    """مدیریت state های پنل ادمین پرداخت"""
    from bot import is_admin, clear_state
    
    if not is_admin(user_id):
        return False
    
    # تنظیم merchant زیبال
    if state == "payment_admin_zibal_merchant":
        merchant_id = message.text.strip()
        
        with db.get_connection() as conn:
            PaymentZibalDB.update_payment_settings(conn, 'zibal', merchant_id=merchant_id)
        
        bot.send_message(
            message.chat.id,
            f"✅ Merchant ID تنظیم شد!\n\n`{merchant_id}`"
        )
        clear_state(user_id)
        return True
    
    # تنظیم callback زیبال
    elif state == "payment_admin_zibal_callback":
        callback_url = message.text.strip()
        
        with db.get_connection() as conn:
            PaymentZibalDB.update_payment_settings(conn, 'zibal', callback_url=callback_url)
        
        bot.send_message(
            message.chat.id,
            f"✅ Callback URL تنظیم شد!\n\n`{callback_url}`"
        )
        clear_state(user_id)
        return True
    
    # تنظیم محدودیت زیبال
    elif state == "payment_admin_zibal_limits":
        try:
            parts = message.text.replace(',', '').split(',')
            if len(parts) != 2:
                bot.send_message(message.chat.id, "❌ فرمت نادرست! از فرمت `حداقل,حداکثر` استفاده کنید.")
                return True
            
            min_amount = int(parts[0])
            max_amount = int(parts[1])
            
            if min_amount >= max_amount:
                bot.send_message(message.chat.id, "❌ حداقل باید کمتر از حداکثر باشد!")
                return True
            
            with db.get_connection() as conn:
                PaymentZibalDB.update_payment_settings(
                    conn, 'zibal',
                    min_amount=min_amount,
                    max_amount=max_amount
                )
            
            bot.send_message(
                message.chat.id,
                f"✅ محدودیت‌ها تنظیم شد!\n\n"
                f"💰 حداقل: {min_amount:,} تومان\n"
                f"💰 حداکثر: {max_amount:,} تومان"
            )
            clear_state(user_id)
            return True
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً اعداد معتبر وارد کنید!")
            return True
    
    # تنظیم API کریپتو
    elif state == "payment_admin_crypto_api":
        api_key = message.text.strip()
        
        with db.get_connection() as conn:
            PaymentZibalDB.update_payment_settings(conn, 'crypto', api_key=api_key)
        
        bot.send_message(
            message.chat.id,
            f"✅ API Key تنظیم شد!\n\n`{api_key[:20]}...`"
        )
        clear_state(user_id)
        return True
    
    # تنظیم callback کریپتو
    elif state == "payment_admin_crypto_callback":
        callback_url = message.text.strip()
        
        with db.get_connection() as conn:
            PaymentZibalDB.update_payment_settings(conn, 'crypto', callback_url=callback_url)
        
        bot.send_message(
            message.chat.id,
            f"✅ Callback URL تنظیم شد!\n\n`{callback_url}`"
        )
        clear_state(user_id)
        return True
    
    return False
