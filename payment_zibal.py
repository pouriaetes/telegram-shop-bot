"""
ماژول پرداخت با درگاه زیبال
مبتنی بر Zibal API v2
"""

import logging
import requests
import json
from datetime import datetime
from typing import Optional, Dict
from telebot import types

logger = logging.getLogger(__name__)

# ===== DATABASE METHODS =====

class PaymentZibalDB:
    """متدهای دیتابیس برای پرداخت زیبال"""
    
    @staticmethod
    def init_tables(conn):
        """ایجاد جداول مورد نیاز"""
        
        # جدول تراکنش‌های زیبال
        conn.execute("""
            CREATE TABLE IF NOT EXISTS zibal_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                track_id INTEGER UNIQUE,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                reference_number TEXT,
                card_number TEXT,
                zibal_status INTEGER,
                description TEXT,
                callback_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                verified_at TIMESTAMP
            )
        """)
        
        # جدول تنظیمات پرداخت
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gateway_type TEXT NOT NULL UNIQUE,
                is_active BOOLEAN DEFAULT 1,
                merchant_id TEXT,
                api_key TEXT,
                callback_url TEXT,
                min_amount INTEGER DEFAULT 10000,
                max_amount INTEGER DEFAULT 50000000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        logger.info("✅ جداول پرداخت زیبال ایجاد شد")
    
    @staticmethod
    def create_transaction(conn, user_id: int, amount: int, description: str = "") -> int:
        """ایجاد تراکنش جدید"""
        cursor = conn.execute("""
            INSERT INTO zibal_transactions (user_id, amount, description, status)
            VALUES (?, ?, ?, 'pending')
        """, (user_id, amount, description))
        return cursor.lastrowid
    
    @staticmethod
    def update_transaction(conn, transaction_id: int, **kwargs):
        """به‌روزرسانی تراکنش"""
        fields = []
        values = []
        
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        
        if not fields:
            return
        
        values.append(transaction_id)
        query = f"UPDATE zibal_transactions SET {', '.join(fields)} WHERE id = ?"
        conn.execute(query, values)
    
    @staticmethod
    def get_transaction(conn, transaction_id: int = None, track_id: int = None):
        """دریافت تراکنش"""
        if transaction_id:
            cursor = conn.execute("SELECT * FROM zibal_transactions WHERE id = ?", (transaction_id,))
        elif track_id:
            cursor = conn.execute("SELECT * FROM zibal_transactions WHERE track_id = ?", (track_id,))
        else:
            return None
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def get_user_transactions(conn, user_id: int, limit: int = 20):
        """دریافت تراکنش‌های کاربر"""
        cursor = conn.execute("""
            SELECT * FROM zibal_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def get_payment_settings(conn, gateway_type: str = 'zibal'):
        """دریافت تنظیمات درگاه"""
        cursor = conn.execute("""
            SELECT * FROM payment_settings WHERE gateway_type = ?
        """, (gateway_type,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def update_payment_settings(conn, gateway_type: str, **kwargs):
        """به‌روزرسانی تنظیمات درگاه"""
        # بررسی وجود
        cursor = conn.execute(
            "SELECT id FROM payment_settings WHERE gateway_type = ?",
            (gateway_type,)
        )
        exists = cursor.fetchone()
        
        if not exists:
            # ایجاد جدید
            conn.execute("""
                INSERT INTO payment_settings (gateway_type, is_active, merchant_id, api_key, callback_url)
                VALUES (?, 1, '', '', '')
            """, (gateway_type,))
        
        # به‌روزرسانی
        fields = []
        values = []
        
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        
        values.append(datetime.now().isoformat())
        fields.append("updated_at = ?")
        
        values.append(gateway_type)
        query = f"UPDATE payment_settings SET {', '.join(fields)} WHERE gateway_type = ?"
        conn.execute(query, values)
    
    @staticmethod
    def get_statistics(conn):
        """آمار پرداخت‌های زیبال"""
        cursor = conn.execute("""
            SELECT COUNT(*) FROM zibal_transactions WHERE status = 'success'
        """)
        successful_count = cursor.fetchone()[0]
        
        cursor = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM zibal_transactions WHERE status = 'success'
        """)
        total_amount = cursor.fetchone()[0]
        
        cursor = conn.execute("""
            SELECT COUNT(*) FROM zibal_transactions WHERE status = 'pending'
        """)
        pending_count = cursor.fetchone()[0]
        
        return {
            "successful_count": successful_count,
            "total_amount": total_amount,
            "pending_count": pending_count
        }


# ===== ZIBAL API CLIENT =====

class ZibalAPI:
    """کلاینت API زیبال"""
    
    BASE_URL = "https://gateway.zibal.ir"
    
    def __init__(self, merchant: str):
        self.merchant = merchant
    
    def request_payment(self, amount: int, callback_url: str, description: str = "", 
                       mobile: str = "", allowed_cards: list = None) -> Dict:
        """درخواست پرداخت"""
        
        url = f"{self.BASE_URL}/v1/request"
        
        payload = {
            "merchant": self.merchant,
            "amount": amount,  # به ریال
            "callbackUrl": callback_url,
            "description": description,
        }
        
        if mobile:
            payload["mobile"] = mobile
        
        if allowed_cards:
            payload["allowedCards"] = allowed_cards
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            logger.info(f"Zibal Request: {result}")
            
            if result.get("result") == 100:
                return {
                    "success": True,
                    "trackId": result.get("trackId"),
                    "payment_url": f"{self.BASE_URL}/start/{result.get('trackId')}"
                }
            else:
                return {
                    "success": False,
                    "error": self._get_error_message(result.get("result")),
                    "code": result.get("result")
                }
        
        except Exception as e:
            logger.error(f"Zibal Request Error: {e}")
            return {"success": False, "error": f"خطا در ارتباط با درگاه: {e}"}
    
    def verify_payment(self, track_id: int) -> Dict:
        """تایید پرداخت"""
        
        url = f"{self.BASE_URL}/v1/verify"
        
        payload = {
            "merchant": self.merchant,
            "trackId": track_id
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            logger.info(f"Zibal Verify: {result}")
            
            if result.get("result") == 100:
                return {
                    "success": True,
                    "paidAt": result.get("paidAt"),
                    "amount": result.get("amount"),
                    "status": result.get("status"),
                    "refNumber": result.get("refNumber"),
                    "description": result.get("description"),
                    "cardNumber": result.get("cardNumber"),
                    "orderId": result.get("orderId")
                }
            else:
                return {
                    "success": False,
                    "error": self._get_error_message(result.get("result")),
                    "code": result.get("result")
                }
        
        except Exception as e:
            logger.error(f"Zibal Verify Error: {e}")
            return {"success": False, "error": f"خطا در تایید پرداخت: {e}"}
    
    @staticmethod
    def _get_error_message(code: int) -> str:
        """دریافت پیام خطا"""
        errors = {
            102: "merchant یافت نشد",
            103: "merchant غیرفعال است",
            104: "merchant نامعتبر است",
            105: "amount باید بیشتر از 1,000 ریال باشد",
            106: "callbackUrl نامعتبر است",
            113: "amount مبلغ بیش از حد تراکنش است",
            201: "قبلاً تایید شده است",
            202: "سفارش پرداخت نشده یا ناموفق بوده است",
            203: "trackId نامعتبر است"
        }
        return errors.get(code, f"خطای ناشناخته (کد {code})")


# ===== HANDLERS =====

class PaymentZibalHandlers:
    """handlers برای پرداخت زیبال"""
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    def register_handlers(self):
        """ثبت handlers"""
        
        self.bot.callback_query_handler(func=lambda c: c.data == "payment_zibal")(self.start_payment)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("zibal_amount_"))(self.select_amount)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("zibal_custom_amount"))(self.custom_amount)
        self.bot.callback_query_handler(func=lambda c: c.data == "zibal_transactions")(self.show_transactions)
    
    def start_payment(self, call):
        """شروع پرداخت زیبال"""
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
        
        if not settings or not settings.get('is_active'):
            self.bot.answer_callback_query(call.id, "❌ درگاه  غیرفعال است!", show_alert=True)
            return
        
        text = (
            f"💳 **شارژ کیف پول با زیبال**\n\n"
            f"مبلغ مورد نظر خود را انتخاب کنید:\n\n"
            f"💰 حداقل: {settings['min_amount']:,} تومان\n"
            f"💰 حداکثر: {settings['max_amount']:,} تومان"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # مبالغ پیشنهادی
        amounts = [10000, 20000, 50000, 100000, 200000, 500000]
        buttons = []
        
        for amount in amounts:
            if settings['min_amount'] <= amount <= settings['max_amount']:
                buttons.append(
                    types.InlineKeyboardButton(
                        f"{amount:,} تومان",
                        callback_data=f"zibal_amount_{amount}"
                    )
                )
        
        # ردیف‌بندی 2تایی
        for i in range(0, len(buttons), 2):
            if i + 1 < len(buttons):
                markup.row(buttons[i], buttons[i + 1])
            else:
                markup.add(buttons[i])
        
        markup.add(
            types.InlineKeyboardButton("💵 مبلغ دلخواه", callback_data="zibal_custom_amount"),
            types.InlineKeyboardButton("📜 تراکنش‌های من", callback_data="zibal_transactions")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def select_amount(self, call):
        """انتخاب مبلغ از لیست"""
        user_id = call.from_user.id
        amount = int(call.data.split("_")[2])
        
        self._process_payment(call, user_id, amount)
    
    def custom_amount(self, call):
        """مبلغ دلخواه"""
        user_id = call.from_user.id
        
        from bot import set_state, user_data
        set_state(user_id, "payment_zibal_waiting_amount")
        user_data[user_id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="payment_zibal"))
        
        self.bot.send_message(
            call.message.chat.id,
            "💵 **مبلغ دلخواه**\n\nمبلغ مورد نظر خود را به تومان وارد کنید:",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def _process_payment(self, call, user_id: int, amount: int):
        """پردازش پرداخت"""
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
            
            if not settings:
                self.bot.answer_callback_query(call.id, "❌ تنظیمات درگاه یافت نشد!", show_alert=True)
                return
            
            # بررسی محدودیت مبلغ
            if amount < settings['min_amount']:
                self.bot.answer_callback_query(
                    call.id,
                    f"❌ حداقل مبلغ {settings['min_amount']:,} تومان است!",
                    show_alert=True
                )
                return
            
            if amount > settings['max_amount']:
                self.bot.answer_callback_query(
                    call.id,
                    f"❌ حداکثر مبلغ {settings['max_amount']:,} تومان است!",
                    show_alert=True
                )
                return
            
            # ایجاد تراکنش
            transaction_id = PaymentZibalDB.create_transaction(
                conn,
                user_id=user_id,
                amount=amount,
                description=f"شارژ کیف پول کاربر {user_id}"
            )
            
            # درخواست پرداخت از زیبال
            zibal = ZibalAPI(settings['merchant_id'])
            
            # callback URL (باید یک سرور webhook داشته باشید)
            # برای ربات تلگرام می‌توانید از Flask/FastAPI استفاده کنید
            callback_url = settings.get('callback_url', 'https://yourdomain.com/zibal/callback')
            
            result = zibal.request_payment(
                amount=amount * 10,  # تبدیل تومان به ریال
                callback_url=callback_url,
                description=f"شارژ کیف پول - تراکنش #{transaction_id}"
            )
            
            if result['success']:
                # به‌روزرسانی تراکنش
                PaymentZibalDB.update_transaction(
                    conn,
                    transaction_id,
                    track_id=result['trackId'],
                    callback_url=callback_url,
                    status='awaiting_payment'
                )
                
                # ارسال لینک پرداخت
                text = (
                    f"✅ **درخواست پرداخت ایجاد شد**\n\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"🔢 کد پیگیری: {result['trackId']}\n\n"
                    f"برای پرداخت، روی دکمه زیر کلیک کنید:"
                )
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💳 پرداخت", url=result['payment_url']))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="payment_zibal"))
                
                self.bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
                
                # پیام راهنما
                self.bot.send_message(
                    call.message.chat.id,
                    "⚠️ پس از پرداخت، به صورت خودکار به ربات بازمی‌گردید.\n"
                    "اگر پرداخت موفق بود، موجودی شما به‌روزرسانی می‌شود."
                )
            else:
                self.bot.answer_callback_query(
                    call.id,
                    f"❌ {result.get('error', 'خطا در ایجاد درخواست')}",
                    show_alert=True
                )
    
    def show_transactions(self, call):
        """نمایش تراکنش‌های کاربر"""
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            transactions = PaymentZibalDB.get_user_transactions(conn, user_id, limit=10)
        
        if not transactions:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="payment_zibal"))
            
            self.bot.edit_message_text(
                "📭 شما هنوز تراکنشی ندارید.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "📜 **تراکنش‌های شما:**\n\n"
        
        status_text = {
            'pending': '⏳ در انتظار',
            'awaiting_payment': '💳 منتظر پرداخت',
            'success': '✅ موفق',
            'failed': '❌ ناموفق',
            'canceled': '🚫 لغو شده'
        }
        
        for tx in transactions[:10]:
            status = status_text.get(tx['status'], tx['status'])
            text += (
                f"🔢 کد پیگیری: {tx['track_id'] or 'ندارد'}\n"
                f"💰 مبلغ: {tx['amount']:,} تومان\n"
                f"📊 وضعیت: {status}\n"
                f"📅 تاریخ: {tx['created_at']}\n\n"
            )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="payment_zibal"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def verify_payment_manual(self, user_id: int, track_id: int):
        """تایید دستی پرداخت (برای استفاده در webhook)"""
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
            transaction = PaymentZibalDB.get_transaction(conn, track_id=track_id)
            
            if not transaction:
                return {"success": False, "error": "تراکنش یافت نشد"}
            
            # اگر قبلاً تایید شده
            if transaction['status'] == 'success':
                return {"success": False, "error": "قبلاً تایید شده است"}
            
            # تایید از زیبال
            zibal = ZibalAPI(settings['merchant_id'])
            result = zibal.verify_payment(track_id)
            
            if result['success']:
                # به‌روزرسانی تراکنش
                PaymentZibalDB.update_transaction(
                    conn,
                    transaction['id'],
                    status='success',
                    reference_number=result.get('refNumber'),
                    card_number=result.get('cardNumber'),
                    zibal_status=result.get('status'),
                    paid_at=result.get('paidAt'),
                    verified_at=datetime.now().isoformat()
                )
                
                # افزودن موجودی کاربر
                conn.execute(
                    "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                    (transaction['amount'], user_id)
                )
                
                # ثبت تراکنش موجودی
                conn.execute("""
                    INSERT INTO transactions (user_id, amount, type, description)
                    VALUES (?, ?, 'deposit', ?)
                """, (user_id, transaction['amount'], f"شارژ کیف پول - زیبال #{track_id}"))
                
                logger.info(f"✅ پرداخت موفق - کاربر: {user_id}, مبلغ: {transaction['amount']}")
                
                return {
                    "success": True,
                    "amount": transaction['amount'],
                    "reference_number": result.get('refNumber')
                }
            else:
                # به‌روزرسانی به وضعیت ناموفق
                PaymentZibalDB.update_transaction(
                    conn,
                    transaction['id'],
                    status='failed'
                )
                
                return {"success": False, "error": result.get('error')}


# ===== MESSAGE HANDLERS برای State Management =====

def handle_payment_zibal_states(bot, db, message, user_id, state, user_data):
    """مدیریت state های پرداخت زیبال"""
    
    if state == "payment_zibal_waiting_amount":
        try:
            amount = int(message.text.replace(',', ''))
            
            with db.get_connection() as conn:
                settings = PaymentZibalDB.get_payment_settings(conn, 'zibal')
            
            if amount < settings['min_amount']:
                bot.send_message(
                    message.chat.id,
                    f"❌ حداقل مبلغ {settings['min_amount']:,} تومان است!"
                )
                return True
            
            if amount > settings['max_amount']:
                bot.send_message(
                    message.chat.id,
                    f"❌ حداکثر مبلغ {settings['max_amount']:,} تومان است!"
                )
                return True
            
            # ایجاد یک callback query ساختگی برای استفاده از _process_payment
            class FakeCall:
                def __init__(self, chat_id, message_id, from_user):
                    self.message = type('obj', (object,), {
                        'chat': type('obj', (object,), {'id': chat_id}),
                        'message_id': message_id
                    })
                    self.from_user = from_user
                    self.id = "fake_callback"
            
            fake_call = FakeCall(message.chat.id, message.message_id, message.from_user)
            
            handlers = PaymentZibalHandlers(bot, db)
            handlers._process_payment(fake_call, user_id, amount)
            
            from bot import clear_state
            clear_state(user_id)
            return True
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
            return True
    
    return False
