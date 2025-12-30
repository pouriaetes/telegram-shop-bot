"""
ماژول پرداخت با ارز دیجیتال
API: NOWPayments
ارزهای پشتیبانی شده: BTC, ETH, USDT, TRX
"""

import logging
import requests
import json
from datetime import datetime
from typing import Optional, Dict, List
from telebot import types
from payment_zibal import PaymentZibalDB

logger = logging.getLogger(__name__)

# ===== DATABASE METHODS =====

class PaymentDigitalDB:
    """متدهای دیتابیس برای پرداخت دیجیتال"""
    
    @staticmethod
    def init_tables(conn):
        """ایجاد جداول مورد نیاز"""
        
        # جدول تراکنش‌های کریپتو
        conn.execute("""
            CREATE TABLE IF NOT EXISTS crypto_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                payment_id TEXT UNIQUE,
                order_id TEXT UNIQUE,
                amount_usd REAL NOT NULL,
                amount_crypto REAL,
                currency TEXT NOT NULL,
                pay_address TEXT,
                payment_status TEXT DEFAULT 'waiting',
                actual_amount_crypto REAL,
                actual_amount_usd REAL,
                network_fee REAL,
                pay_amount REAL,
                purchase_id TEXT,
                description TEXT,
                ipn_callback_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expired_at TIMESTAMP,
                finished_at TIMESTAMP
            )
        """)
        
        # جدول نرخ ارز
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                currency_from TEXT NOT NULL,
                currency_to TEXT NOT NULL,
                rate REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(currency_from, currency_to)
            )
        """)
        
        logger.info("✅ جداول پرداخت دیجیتال ایجاد شد")
    
    @staticmethod
    def create_transaction(conn, user_id: int, amount_usd: float, currency: str, description: str = "") -> int:
        """ایجاد تراکنش جدید"""
        import uuid
        order_id = f"ORDER-{user_id}-{int(datetime.now().timestamp())}"
        
        cursor = conn.execute("""
            INSERT INTO crypto_transactions 
            (user_id, order_id, amount_usd, currency, description, payment_status)
            VALUES (?, ?, ?, ?, ?, 'waiting')
        """, (user_id, order_id, amount_usd, currency, description))
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
        
        fields.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        
        values.append(transaction_id)
        query = f"UPDATE crypto_transactions SET {', '.join(fields)} WHERE id = ?"
        conn.execute(query, values)
    
    @staticmethod
    def get_transaction(conn, transaction_id: int = None, payment_id: str = None, order_id: str = None):
        """دریافت تراکنش"""
        if transaction_id:
            cursor = conn.execute("SELECT * FROM crypto_transactions WHERE id = ?", (transaction_id,))
        elif payment_id:
            cursor = conn.execute("SELECT * FROM crypto_transactions WHERE payment_id = ?", (payment_id,))
        elif order_id:
            cursor = conn.execute("SELECT * FROM crypto_transactions WHERE order_id = ?", (order_id,))
        else:
            return None
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def get_user_transactions(conn, user_id: int, limit: int = 20):
        """دریافت تراکنش‌های کاربر"""
        cursor = conn.execute("""
            SELECT * FROM crypto_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def update_exchange_rate(conn, currency_from: str, currency_to: str, rate: float):
        """به‌روزرسانی نرخ ارز"""
        conn.execute("""
            INSERT OR REPLACE INTO exchange_rates (currency_from, currency_to, rate, updated_at)
            VALUES (?, ?, ?, ?)
        """, (currency_from, currency_to, rate, datetime.now().isoformat()))
    
    @staticmethod
    def get_exchange_rate(conn, currency_from: str, currency_to: str):
        """دریافت نرخ ارز"""
        cursor = conn.execute("""
            SELECT rate, updated_at FROM exchange_rates
            WHERE currency_from = ? AND currency_to = ?
        """, (currency_from, currency_to))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def get_statistics(conn):
        """آمار پرداخت‌های دیجیتال"""
        cursor = conn.execute("""
            SELECT COUNT(*) FROM crypto_transactions WHERE payment_status = 'finished'
        """)
        successful_count = cursor.fetchone()[0]
        
        cursor = conn.execute("""
            SELECT COALESCE(SUM(actual_amount_usd), 0) FROM crypto_transactions 
            WHERE payment_status = 'finished'
        """)
        total_amount_usd = cursor.fetchone()[0]
        
        cursor = conn.execute("""
            SELECT COUNT(*) FROM crypto_transactions WHERE payment_status = 'waiting'
        """)
        pending_count = cursor.fetchone()[0]
        
        return {
            "successful_count": successful_count,
            "total_amount_usd": total_amount_usd,
            "pending_count": pending_count
        }


# ===== NOWPAYMENTS API CLIENT =====

class NOWPaymentsAPI:
    """کلاینت API NOWPayments"""
    
    BASE_URL = "https://api.nowpayments.io/v1"
    
    def __init__(self, api_key: str, ipn_secret: str = ""):
        self.api_key = api_key
        self.ipn_secret = ipn_secret
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
    
    def get_available_currencies(self) -> List[str]:
        """دریافت لیست ارزهای موجود"""
        try:
            response = requests.get(f"{self.BASE_URL}/currencies", headers=self.headers, timeout=10)
            result = response.json()
            return result.get("currencies", [])
        except Exception as e:
            logger.error(f"NOWPayments currencies error: {e}")
            return []
    
    def get_estimate(self, amount: float, currency_from: str, currency_to: str) -> Dict:
        """تخمین مبلغ"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/estimate",
                params={
                    "amount": amount,
                    "currency_from": currency_from,
                    "currency_to": currency_to
                },
                headers=self.headers,
                timeout=10
            )
            result = response.json()
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "estimated_amount": result.get("estimated_amount"),
                    "currency_from": result.get("currency_from"),
                    "currency_to": result.get("currency_to")
                }
            else:
                return {"success": False, "error": result.get("message", "خطا در تخمین")}
        
        except Exception as e:
            logger.error(f"NOWPayments estimate error: {e}")
            return {"success": False, "error": str(e)}
    
    def create_payment(self, price_amount: float, price_currency: str, pay_currency: str,
                      order_id: str, order_description: str = "", ipn_callback_url: str = "") -> Dict:
        """ایجاد پرداخت"""
        
        payload = {
            "price_amount": price_amount,
            "price_currency": price_currency,
            "pay_currency": pay_currency,
            "order_id": order_id,
            "order_description": order_description
        }
        
        if ipn_callback_url:
            payload["ipn_callback_url"] = ipn_callback_url
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/payment",
                json=payload,
                headers=self.headers,
                timeout=10
            )
            result = response.json()
            
            logger.info(f"NOWPayments create payment: {result}")
            
            if response.status_code in [200, 201]:
                return {
                    "success": True,
                    "payment_id": result.get("payment_id"),
                    "payment_status": result.get("payment_status"),
                    "pay_address": result.get("pay_address"),
                    "price_amount": result.get("price_amount"),
                    "price_currency": result.get("price_currency"),
                    "pay_amount": result.get("pay_amount"),
                    "pay_currency": result.get("pay_currency"),
                    "order_id": result.get("order_id"),
                    "order_description": result.get("order_description"),
                    "ipn_callback_url": result.get("ipn_callback_url"),
                    "created_at": result.get("created_at"),
                    "updated_at": result.get("updated_at"),
                    "purchase_id": result.get("purchase_id")
                }
            else:
                return {
                    "success": False,
                    "error": result.get("message", "خطا در ایجاد پرداخت")
                }
        
        except Exception as e:
            logger.error(f"NOWPayments create payment error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_payment_status(self, payment_id: str) -> Dict:
        """دریافت وضعیت پرداخت"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/payment/{payment_id}",
                headers=self.headers,
                timeout=10
            )
            result = response.json()
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "payment_id": result.get("payment_id"),
                    "payment_status": result.get("payment_status"),
                    "pay_address": result.get("pay_address"),
                    "price_amount": result.get("price_amount"),
                    "price_currency": result.get("price_currency"),
                    "pay_amount": result.get("pay_amount"),
                    "actually_paid": result.get("actually_paid"),
                    "pay_currency": result.get("pay_currency"),
                    "order_id": result.get("order_id"),
                    "order_description": result.get("order_description"),
                    "purchase_id": result.get("purchase_id"),
                    "outcome_amount": result.get("outcome_amount"),
                    "outcome_currency": result.get("outcome_currency")
                }
            else:
                return {"success": False, "error": result.get("message", "خطا در دریافت وضعیت")}
        
        except Exception as e:
            logger.error(f"NOWPayments get status error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_minimum_payment_amount(self, currency: str) -> Dict:
        """دریافت حداقل مبلغ پرداخت"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/min-amount",
                params={"currency_from": "usd", "currency_to": currency},
                headers=self.headers,
                timeout=10
            )
            result = response.json()
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "min_amount": result.get("min_amount")
                }
            else:
                return {"success": False, "error": result.get("message")}
        
        except Exception as e:
            logger.error(f"NOWPayments min amount error: {e}")
            return {"success": False, "error": str(e)}


# ===== HANDLERS =====

class PaymentDigitalHandlers:
    """handlers برای پرداخت دیجیتال"""
    
    # ارزهای پشتیبانی شده
    SUPPORTED_CURRENCIES = {
        "btc": {"name": "Bitcoin", "emoji": "₿", "min_usd": 5},
        "eth": {"name": "Ethereum", "emoji": "Ξ", "min_usd": 5},
        "usdt": {"name": "Tether (USDT)", "emoji": "₮", "min_usd": 5},
        "trx": {"name": "Tron (TRX)", "emoji": "🔺", "min_usd": 5}
    }
    
    # نرخ تبدیل تومان به دلار (باید از API دریافت شود)
    USD_TO_TOMAN_RATE = 65000  # به‌روزرسانی شود
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    def register_handlers(self):
        """ثبت handlers"""
        
        self.bot.callback_query_handler(func=lambda c: c.data == "payment_digital")(self.start_payment)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("crypto_select_"))(self.select_currency)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("crypto_amount_"))(self.select_amount)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("crypto_custom_amount_"))(self.custom_amount)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("crypto_pay_"))(self.process_payment)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("crypto_check_"))(self.check_payment_status)
        self.bot.callback_query_handler(func=lambda c: c.data == "crypto_transactions")(self.show_transactions)
    
    def start_payment(self, call):
        """شروع پرداخت کریپتو"""
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        if not settings or not settings.get('is_active'):
            self.bot.answer_callback_query(call.id, "❌ پرداخت ارز دیجیتال غیرفعال است!", show_alert=True)
            return
        
        text = (
            f"💎 **پرداخت با ارز دیجیتال**\n\n"
            f"ارز مورد نظر خود را انتخاب کنید:\n\n"
            f"✅ پرداخت سریع و امن\n"
            f"✅ بدون نیاز به کارت بانکی\n"
            f"✅ کارمزد کم"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        for currency, info in self.SUPPORTED_CURRENCIES.items():
            markup.add(
                types.InlineKeyboardButton(
                    f"{info['emoji']} {info['name']}",
                    callback_data=f"crypto_select_{currency}"
                )
            )
        
        markup.add(
            types.InlineKeyboardButton("📜 تراکنش‌های من", callback_data="crypto_transactions"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def select_currency(self, call):
        """انتخاب ارز"""
        user_id = call.from_user.id
        currency = call.data.split("_")[2]
        
        if currency not in self.SUPPORTED_CURRENCIES:
            self.bot.answer_callback_query(call.id, "❌ ارز نامعتبر!", show_alert=True)
            return
        
        info = self.SUPPORTED_CURRENCIES[currency]
        
        text = (
            f"{info['emoji']} **پرداخت با {info['name']}**\n\n"
            f"مبلغ مورد نظر خود را به تومان انتخاب کنید:\n\n"
            f"💵 حداقل: {info['min_usd'] * self.USD_TO_TOMAN_RATE:,.0f} تومان"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # مبالغ پیشنهادی (تومان)
        amounts_toman = [50000, 100000, 200000, 500000, 1000000, 2000000]
        buttons = []
        
        for amount in amounts_toman:
            amount_usd = amount / self.USD_TO_TOMAN_RATE
            if amount_usd >= info['min_usd']:
                buttons.append(
                    types.InlineKeyboardButton(
                        f"{amount:,} تومان",
                        callback_data=f"crypto_amount_{currency}_{amount}"
                    )
                )
        
        # ردیف‌بندی 2تایی
        for i in range(0, len(buttons), 2):
            if i + 1 < len(buttons):
                markup.row(buttons[i], buttons[i + 1])
            else:
                markup.add(buttons[i])
        
        markup.add(
            types.InlineKeyboardButton("💵 مبلغ دلخواه", callback_data=f"crypto_custom_amount_{currency}")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="payment_digital"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def select_amount(self, call):
        """انتخاب مبلغ از لیست"""
        user_id = call.from_user.id
        parts = call.data.split("_")
        currency = parts[2]
        amount_toman = int(parts[3])
        
        self._show_payment_confirmation(call, user_id, currency, amount_toman)
    
    def custom_amount(self, call):
        """مبلغ دلخواه"""
        user_id = call.from_user.id
        currency = call.data.split("_")[3]
        
        from bot import set_state, user_data
        set_state(user_id, f"payment_crypto_waiting_amount_{currency}")
        user_data[user_id] = {'currency': currency}
        
        info = self.SUPPORTED_CURRENCIES[currency]
        min_toman = info['min_usd'] * self.USD_TO_TOMAN_RATE
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"crypto_select_{currency}"))
        
        self.bot.send_message(
            call.message.chat.id,
            f"💵 **مبلغ دلخواه**\n\n"
            f"مبلغ مورد نظر خود را به تومان وارد کنید:\n\n"
            f"⚠️ حداقل: {min_toman:,.0f} تومان",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def _show_payment_confirmation(self, call, user_id: int, currency: str, amount_toman: int):
        """نمایش تایید پرداخت"""
        
        info = self.SUPPORTED_CURRENCIES[currency]
        amount_usd = amount_toman / self.USD_TO_TOMAN_RATE
        
        # بررسی حداقل مبلغ
        if amount_usd < info['min_usd']:
            self.bot.answer_callback_query(
                call.id,
                f"❌ حداقل {info['min_usd']} دلار است!",
                show_alert=True
            )
            return
        
        # دریافت تخمین از NOWPayments
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
        
        if not settings or not settings.get('api_key'):
            self.bot.answer_callback_query(call.id, "❌ تنظیمات API یافت نشد!", show_alert=True)
            return
        
        nowpayments = NOWPaymentsAPI(settings['api_key'])
        estimate = nowpayments.get_estimate(amount_usd, "usd", currency)
        
        if not estimate['success']:
            self.bot.answer_callback_query(call.id, f"❌ {estimate.get('error')}", show_alert=True)
            return
        
        crypto_amount = estimate['estimated_amount']
        
        text = (
            f"{info['emoji']} **تایید پرداخت**\n\n"
            f"💰 مبلغ: {amount_toman:,} تومان\n"
            f"💵 معادل: ${amount_usd:.2f}\n"
            f"🪙 پرداختی: {crypto_amount} {currency.upper()}\n\n"
            f"⚠️ بعد از تایید، آدرس کیف پول برای پرداخت ارسال می‌شود.\n"
            f"⏰ مهلت پرداخت: 30 دقیقه"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ تایید و پرداخت", callback_data=f"crypto_pay_{currency}_{amount_toman}")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"crypto_select_{currency}"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def process_payment(self, call):
        """پردازش پرداخت"""
        user_id = call.from_user.id
        parts = call.data.split("_")
        currency = parts[2]
        amount_toman = int(parts[3])
        
        amount_usd = amount_toman / self.USD_TO_TOMAN_RATE
        info = self.SUPPORTED_CURRENCIES[currency]
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
            
            # ایجاد تراکنش
            transaction_id = PaymentDigitalDB.create_transaction(
                conn,
                user_id=user_id,
                amount_usd=amount_usd,
                currency=currency,
                description=f"شارژ کیف پول - کاربر {user_id}"
            )
            
            transaction = PaymentDigitalDB.get_transaction(conn, transaction_id=transaction_id)
        
        # ایجاد پرداخت در NOWPayments
        nowpayments = NOWPaymentsAPI(settings['api_key'])
        
        ipn_callback = settings.get('callback_url', '')
        
        result = nowpayments.create_payment(
            price_amount=amount_usd,
            price_currency="usd",
            pay_currency=currency,
            order_id=transaction['order_id'],
            order_description=f"شارژ کیف پول - تراکنش #{transaction_id}",
            ipn_callback_url=ipn_callback
        )
        
        if result['success']:
            # به‌روزرسانی تراکنش
            with self.db.get_connection() as conn:
                PaymentDigitalDB.update_transaction(
                    conn,
                    transaction_id,
                    payment_id=result['payment_id'],
                    pay_address=result['pay_address'],
                    pay_amount=result['pay_amount'],
                    amount_crypto=result['pay_amount'],
                    payment_status=result['payment_status'],
                    purchase_id=result.get('purchase_id'),
                    ipn_callback_url=result.get('ipn_callback_url')
                )
            
            # ارسال اطلاعات پرداخت
            text = (
                f"{info['emoji']} **آدرس پرداخت آماده است!**\n\n"
                f"💰 مبلغ: {amount_toman:,} تومان\n"
                f"💵 معادل: ${amount_usd:.2f}\n"
                f"🪙 پرداختی: `{result['pay_amount']}` {currency.upper()}\n\n"
                f"📍 **آدرس کیف پول:**\n`{result['pay_address']}`\n\n"
                f"🔢 شماره پرداخت: `{result['payment_id']}`\n\n"
                f"⏰ مهلت: 30 دقیقه\n"
                f"⚠️ دقیقاً همان مبلغ را ارسال کنید!"
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "🔄 بررسی وضعیت",
                    callback_data=f"crypto_check_{transaction_id}"
                )
            )
            markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
            
            self.bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
            # پیام راهنما
            self.bot.send_message(
                call.message.chat.id,
                "💡 **راهنما:**\n\n"
                "1️⃣ آدرس را کپی کنید\n"
                "2️⃣ به کیف پول خود بروید\n"
                "3️⃣ دقیقاً همان مبلغ را به آدرس بالا ارسال کنید\n"
                "4️⃣ بعد از ارسال، روی 'بررسی وضعیت' کلیک کنید\n\n"
                "✅ بعد از تایید شبکه، موجودی شما به‌روزرسانی می‌شود."
            )
        else:
            self.bot.answer_callback_query(
                call.id,
                f"❌ {result.get('error')}",
                show_alert=True
            )
    
    def check_payment_status(self, call):
        """بررسی وضعیت پرداخت"""
        user_id = call.from_user.id
        transaction_id = int(call.data.split("_")[2])
        
        with self.db.get_connection() as conn:
            settings = PaymentZibalDB.get_payment_settings(conn, 'crypto')
            transaction = PaymentDigitalDB.get_transaction(conn, transaction_id=transaction_id)
        
        if not transaction or transaction['user_id'] != user_id:
            self.bot.answer_callback_query(call.id, "❌ تراکنش یافت نشد!", show_alert=True)
            return
        
        # دریافت وضعیت از NOWPayments
        nowpayments = NOWPaymentsAPI(settings['api_key'])
        status_result = nowpayments.get_payment_status(transaction['payment_id'])
        
        if status_result['success']:
            new_status = status_result['payment_status']
            
            # به‌روزرسانی وضعیت
            with self.db.get_connection() as conn:
                PaymentDigitalDB.update_transaction(
                    conn,
                    transaction_id,
                    payment_status=new_status,
                    actual_amount_crypto=status_result.get('actually_paid'),
                    actual_amount_usd=status_result.get('outcome_amount')
                )
                
                # اگر پرداخت تکمیل شد
                if new_status == 'finished':
                    PaymentDigitalDB.update_transaction(
                        conn,
                        transaction_id,
                        finished_at=datetime.now().isoformat()
                    )
                    
                    # افزودن موجودی
                    amount_toman = int(transaction['amount_usd'] * self.USD_TO_TOMAN_RATE)
                    
                    conn.execute(
                        "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                        (amount_toman, user_id)
                    )
                    
                    # ثبت تراکنش موجودی
                    conn.execute("""
                        INSERT INTO transactions (user_id, amount, type, description)
                        VALUES (?, ?, 'deposit', ?)
                    """, (user_id, amount_toman, f"شارژ کیف پول - کریپتو {transaction['currency'].upper()}"))
                    
                    self.bot.answer_callback_query(
                        call.id,
                        f"✅ پرداخت موفق! موجودی شما {amount_toman:,} تومان افزایش یافت.",
                        show_alert=True
                    )
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
                    
                    self.bot.send_message(
                        call.message.chat.id,
                        f"🎉 **پرداخت موفقیت‌آمیز!**\n\n"
                        f"💰 موجودی جدید شما: {amount_toman:,} تومان\n\n"
                        f"✅ از خرید شما متشکریم!",
                        reply_markup=markup
                    )
                
                elif new_status == 'waiting':
                    self.bot.answer_callback_query(
                        call.id,
                        "⏳ در انتظار پرداخت...\nلطفاً ارز را به آدرس ارسال کنید.",
                        show_alert=True
                    )
                
                elif new_status == 'confirming':
                    self.bot.answer_callback_query(
                        call.id,
                        "🔄 در حال تایید شبکه...\nلطفاً کمی صبر کنید.",
                        show_alert=True
                    )
                
                elif new_status == 'sending':
                    self.bot.answer_callback_query(
                        call.id,
                        "📤 در حال ارسال به کیف پول...",
                        show_alert=True
                    )
                
                elif new_status in ['failed', 'expired']:
                    self.bot.answer_callback_query(
                        call.id,
                        f"❌ پرداخت ناموفق یا منقضی شد.",
                        show_alert=True
                    )
        else:
            self.bot.answer_callback_query(
                call.id,
                f"❌ خطا در دریافت وضعیت",
                show_alert=True
            )
    
    def show_transactions(self, call):
        """نمایش تراکنش‌های کاربر"""
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            transactions = PaymentDigitalDB.get_user_transactions(conn, user_id, limit=10)
        
        if not transactions:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="payment_digital"))
            
            self.bot.edit_message_text(
                "📭 شما هنوز تراکنشی ندارید.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "📜 **تراکنش‌های ارز دیجیتال:**\n\n"
        
        status_text = {
            'waiting': '⏳ در انتظار',
            'confirming': '🔄 در حال تایید',
            'sending': '📤 در حال ارسال',
            'finished': '✅ موفق',
            'failed': '❌ ناموفق',
            'expired': '⏰ منقضی شده'
        }
        
        for tx in transactions[:10]:
            status = status_text.get(tx['payment_status'], tx['payment_status'])
            currency_info = self.SUPPORTED_CURRENCIES.get(tx['currency'], {})
            emoji = currency_info.get('emoji', '🪙')
            
            text += (
                f"{emoji} {tx['currency'].upper()}\n"
                f"💰 مبلغ: ${tx['amount_usd']:.2f}\n"
                f"📊 وضعیت: {status}\n"
                f"📅 تاریخ: {tx['created_at']}\n\n"
            )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="payment_digital"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)


# ===== MESSAGE HANDLERS برای State Management =====

def handle_payment_digital_states(bot, db, message, user_id, state, user_data):
    """مدیریت state های پرداخت دیجیتال"""
    
    if state.startswith("payment_crypto_waiting_amount_"):
        currency = state.split("_")[-1]
        
        try:
            amount_toman = int(message.text.replace(',', ''))
            
            handlers = PaymentDigitalHandlers(bot, db)
            info = handlers.SUPPORTED_CURRENCIES.get(currency)
            
            if not info:
                bot.send_message(message.chat.id, "❌ ارز نامعتبر!")
                from bot import clear_state
                clear_state(user_id)
                return True
            
            min_toman = info['min_usd'] * handlers.USD_TO_TOMAN_RATE
            
            if amount_toman < min_toman:
                bot.send_message(
                    message.chat.id,
                    f"❌ حداقل مبلغ {min_toman:,.0f} تومان است!"
                )
                return True
            
            # ایجاد callback ساختگی
            class FakeCall:
                def __init__(self, chat_id, message_id, from_user):
                    self.message = type('obj', (object,), {
                        'chat': type('obj', (object,), {'id': chat_id}),
                        'message_id': message_id
                    })
                    self.from_user = from_user
                    self.id = "fake_callback"
            
            fake_call = FakeCall(message.chat.id, message.message_id, message.from_user)
            
            handlers._show_payment_confirmation(fake_call, user_id, currency, amount_toman)
            
            from bot import clear_state
            clear_state(user_id)
            return True
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ لطفاً یک عدد معتبر وارد کنید!")
            return True
    
    return False
