"""
ماژول خرید اکانت سفارشی (Account Maker)
این ماژول کاملاً مجزا از سیستم فروش محصولات معمولی است
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List
from telebot import types
import json

logger = logging.getLogger(__name__)
# ===== بدون دیتابیس - ذخیره موقت در حافظه =====
import time

# ذخیره سفارشات موقت (بدون دیتابیس)
pending_orders = {}
order_counter = 1

# اطلاعات محصول ChatGPT GO
CHATGPT_GO_PRODUCT = {
    "name": "🛡️ ChatGPT GO",
    "description": """این اکانت کرک ‌شده است و به همین دلیل، قیمت آن پایین‌تر از قیمت اصلی سایت رسمی می‌باشد.""",
    "rules": """📋 قوانین:
1. این حساب هیچ پشتیبانی‌ای ندارد (به جز در هفته اول، تنها در صورت غیرفعال شدن حساب).
2. این حساب یک حساب کاربری معمولی است که مستقیماً از OpenAI دریافت شده؛ بنابراین، حتماً از VPN معتبر استفاده کنید.
3. استفاده همزمان چندین کاربر از این حساب ممکن است در طول زمان منجر به مسدود شدن حساب شما شود (هیچ گونه پشتیبانی یا بازگشت وجه وجود نخواهد داشت).
4. این حساب به مدت یک سال برای شما فعال خواهد بود.
5. این حساب روی ایمیل شخصی شما ساخته و فعال می‌شود؛ فقط باید روی آن ایمیل هیچ حسابی از قبل وجود نداشته باشد (برای امنیت بیشتر بهتر است از یک ایمیل جدید استفاده کنید).
6. این حساب به قیمت 1,499,000 تومان به فروش می‌رسد.""",
    "price": 1499000,
    "delivery_time": 5
}

# سیستم کد تخفیف
DISCOUNT_CODES = {
    'WELCOME10': {'percent': 10, 'max_uses': 100, 'used': 0},
    'CHATGPT20': {'percent': 20, 'max_uses': 50, 'used': 0}
}

# ===== DATABASE METHODS =====

class AccountMakerDB:
    """متدهای دیتابیس برای Account Maker"""
    
    @staticmethod
    def init_tables(conn):
        """ایجاد جداول مورد نیاز"""
        
        # جدول نوع اکانت‌های سفارشی
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_account_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                rules TEXT,
                price REAL NOT NULL,
                delivery_time_hours INTEGER DEFAULT 4,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # جدول سفارشات اکانت سفارشی
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_account_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_type_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                payment_status TEXT DEFAULT 'unpaid',
                admin_notes TEXT,
                account_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                delivered_at TIMESTAMP,
                FOREIGN KEY (account_type_id) REFERENCES custom_account_types(id)
            )
        """)
        
        logger.info("✅ جداول Account Maker ایجاد شد")
    
    @staticmethod
    def add_account_type(conn, name: str, description: str, rules: str, price: float, delivery_time_hours: int = 4):
        """افزودن نوع اکانت سفارشی"""
        cursor = conn.execute("""
            INSERT INTO custom_account_types (name, description, rules, price, delivery_time_hours)
            VALUES (?, ?, ?, ?, ?)
        """, (name, description, rules, price, delivery_time_hours))
        return cursor.lastrowid
    
    @staticmethod
    def get_active_account_types(conn):
        """دریافت انواع اکانت فعال"""
        cursor = conn.execute("""
            SELECT * FROM custom_account_types
            WHERE is_active = 1
            ORDER BY id
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def get_all_account_types(conn):
        """دریافت همه انواع اکانت"""
        cursor = conn.execute("SELECT * FROM custom_account_types ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def get_account_type(conn, type_id: int):
        """دریافت یک نوع اکانت"""
        cursor = conn.execute("SELECT * FROM custom_account_types WHERE id = ?", (type_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def update_account_type(conn, type_id: int, **kwargs):
        """به‌روزرسانی نوع اکانت"""
        fields = []
        values = []
        
        for key, value in kwargs.items():
            if value is not None:
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
        
        values.append(type_id)
        query = f"UPDATE custom_account_types SET {', '.join(fields)} WHERE id = ?"
        conn.execute(query, values)
        return True
    
    @staticmethod
    def toggle_account_type_status(conn, type_id: int):
        """تغییر وضعیت نوع اکانت"""
        conn.execute("UPDATE custom_account_types SET is_active = NOT is_active WHERE id = ?", (type_id,))
    
    @staticmethod
    def delete_account_type(conn, type_id: int):
        """حذف نوع اکانت"""
        # بررسی وجود سفارشات
        cursor = conn.execute(
            "SELECT COUNT(*) FROM custom_account_orders WHERE account_type_id = ?",
            (type_id,)
        )
        count = cursor.fetchone()[0]
        
        if count > 0:
            return {"error": f"این نوع اکانت دارای {count} سفارش است و قابل حذف نیست"}
        
        conn.execute("DELETE FROM custom_account_types WHERE id = ?", (type_id,))
        return {"success": True}
    
    # در کلاس AccountMakerDB، متد create_order را تغییر دهید:

    @staticmethod
    def create_order(conn, user_id: int, account_type_id: int, email: str, password: str):
        """ایجاد سفارش جدید"""
        cursor = conn.execute("""
            INSERT INTO custom_account_orders 
            (user_id, account_type_id, email, password, status, payment_status)
            VALUES (?, ?, ?, ?, 'waiting_admin_approval', 'unpaid')
        """, (user_id, account_type_id, email, password))
        return cursor.lastrowid

    
    @staticmethod
    def get_order(conn, order_id: int):
        """دریافت سفارش"""
        cursor = conn.execute("""
            SELECT co.*, cat.name as account_type_name, cat.price, cat.delivery_time_hours
            FROM custom_account_orders co
            JOIN custom_account_types cat ON co.account_type_id = cat.id
            WHERE co.id = ?
        """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def update_order_status(conn, order_id: int, status: str, **kwargs):
        """به‌روزرسانی وضعیت سفارش"""
        fields = ["status = ?"]
        values = [status]
        
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        
        values.append(order_id)
        query = f"UPDATE custom_account_orders SET {', '.join(fields)} WHERE id = ?"
        conn.execute(query, values)
    
    @staticmethod
    def get_user_orders(conn, user_id: int):
        """دریافت سفارشات کاربر"""
        cursor = conn.execute("""
            SELECT co.*, cat.name as account_type_name, cat.price
            FROM custom_account_orders co
            JOIN custom_account_types cat ON co.account_type_id = cat.id
            WHERE co.user_id = ?
            ORDER BY co.created_at DESC
            LIMIT 20
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def get_pending_orders(conn):
        """دریافت سفارشات در انتظار"""
        cursor = conn.execute("""
            SELECT co.*, cat.name as account_type_name, cat.price
            FROM custom_account_orders co
            JOIN custom_account_types cat ON co.account_type_id = cat.id
            WHERE co.status IN ('waiting_admin_approval', 'waiting_email_confirmation', 'confirmed', 'paid')
            ORDER BY co.created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    
    @staticmethod
    def get_statistics(conn):
        """آمار اکانت‌های سفارشی"""
        cursor = conn.execute("SELECT COUNT(*) FROM custom_account_orders WHERE status = 'delivered'")
        delivered_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM custom_account_orders WHERE status IN ('waiting_confirmation', 'confirmed', 'paid')")
        pending_count = cursor.fetchone()[0]
        
        cursor = conn.execute("""
            SELECT COALESCE(SUM(cat.price), 0)
            FROM custom_account_orders co
            JOIN custom_account_types cat ON co.account_type_id = cat.id
            WHERE co.payment_status = 'paid'
        """)
        total_revenue = cursor.fetchone()[0]
        
        return {
            "delivered_count": delivered_count,
            "pending_count": pending_count,
            "total_revenue": total_revenue
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
        self.bot.callback_query_handler(func=lambda c: c.data == 'chatgpt_go_start_purchase')(self.start_purchase_flow)  # جدید
        self.bot.callback_query_handler(func=lambda c: c.data == "my_custom_orders")(self.show_my_orders)
        
        # Admin handlers
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_approve_"))(self.admin_approve_order)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_reject_"))(self.admin_reject_order)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_deliver_"))(self.admin_deliver_order)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_acc_pending_orders")(self.admin_pending_orders)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_acc_order_"))(self.admin_show_order)

   
    # ===== USER HANDLERS =====
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
        markup.add(types.InlineKeyboardButton(
            "✅ ادامه خرید", 
            callback_data='chatgpt_go_start_purchase'
        ))
        markup.add(types.InlineKeyboardButton(
            "📦 سفارشات من", 
            callback_data='my_custom_orders'
        ))
        markup.add(types.InlineKeyboardButton(
            "🔙 بازگشت", 
            callback_data='back_to_main'
        ))
        
        self.bot.edit_message_text(
            text, 
            call.message.chat.id, 
            call.message.message_id,
            reply_markup=markup
        )
    def start_purchase_flow(self, call):
        """شروع فرآیند خرید ChatGPT GO"""
        global order_counter, pending_orders
        user_id = call.from_user.id
        
        # ایجاد order_id جدید
        order_id = f"CGPT_{order_counter}_{int(time.time())}"
        order_counter += 1
        
        # ذخیره اطلاعات اولیه
        pending_orders[order_id] = {
            'user_id': user_id,
            'username': call.from_user.username,
            'status': 'waiting_email',
            'created_at': time.time(),
            'product': 'ChatGPT GO'
        }
        
        from bot import user_data, set_state
        user_data[user_id] = {'order_id': order_id}
        set_state(user_id, 'chatgpt_go_waiting_email')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data='account_maker'))
        
        self.bot.send_message(
            call.message.chat.id,
            f"""📧 **مرحله 2 از 6: ارسال ایمیل**

    لطفاً ایمیل خود را ارسال کنید:
    (این ایمیل نباید قبلاً در OpenAI ثبت شده باشد)

    ⚠️ توجه: از یک ایمیل جدید برای امنیت بیشتر استفاده کنید.""",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)


    def confirm_email(self, call):
        """تایید ایمیل توسط کاربر"""
        order_id = int(call.data.split("_")[3])
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
            
            if not order or order['user_id'] != user_id:
                self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
                return
            
            if order['status'] != 'waiting_email_confirmation':
                self.bot.answer_callback_query(call.id, "⚠️ این مرحله قبلاً انجام شده است!", show_alert=True)
                return
            
            # به‌روزرسانی وضعیت
            AccountMakerDB.update_order_status(conn, order_id, 'confirmed')
        
        text = (
            f"⏳ **مرحله 4 از 5: در انتظار اکانت**\n\n"
            f"✅ ایمیل شما تایید شد!\n\n"
            f"اکانت شما طی **{order['delivery_time_hours']} ساعت** آینده آماده خواهد شد.\n"
            f"پس از آماده شدن، به شما اطلاع‌رسانی خواهد شد.\n\n"
            
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("💳 پرداخت", callback_data=f"acc_pay_{order_id}"),
            types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        
        # اطلاع به ادمین‌ها
        self.notify_admins_email_confirmed(order_id)

    def notify_admins_email_confirmed(self, order_id: int):
        """اطلاع به ادمین - ایمیل تایید شد"""
        from config import config
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"✅ **ایمیل تایید شد!**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"👤 کاربر: {order['user_id']}\n"
            f"🎮 نوع: {order['account_type_name']}\n"
            f"📧 ایمیل: {order['email']}\n"
            f"💰 مبلغ: {order['price']:,.0f} تومان\n\n"
            f"⏳ منتظر پرداخت است."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👁 مشاهده سفارش", callback_data=f"admin_acc_order_{order_id}"))
        
        for admin_id in config.admin_list:
            try:
                self.bot.send_message(admin_id, text, reply_markup=markup)
            except:
                pass

    def process_payment(self, call):
        """پردازش پرداخت"""
        order_id = int(call.data.split("_")[2])
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
            
            if not order or order['user_id'] != user_id:
                self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
                return
            
            # بررسی موجودی
            cursor = conn.execute("SELECT balance FROM users WHERE telegram_id = ?", (user_id,))
            user_balance = cursor.fetchone()[0]
            
            if user_balance < order['price']:
                self.bot.answer_callback_query(
                    call.id,
                    f"❌ موجودی ناکافی!\n\nموجودی شما: {user_balance:,.0f} تومان\nمبلغ مورد نیاز: {order['price']:,.0f} تومان",
                    show_alert=True
                )
                return
            
            # کسر موجودی
            conn.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (order['price'], user_id))
            
            # ثبت تراکنش
            conn.execute("""
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, 'purchase', ?)
            """, (user_id, order['price'], f"خرید اکانت سفارشی #{order_id}"))
            
            # به‌روزرسانی سفارش
            AccountMakerDB.update_order_status(
                conn, order_id, 'paid',
                payment_status='paid',
                paid_at=datetime.now().isoformat()
            )
        
        text = (
            f"✅ **پرداخت موفق!**\n\n"
            f"💰 مبلغ پرداختی: {order['price']:,.0f} تومان\n"
            f"🆔 شماره سفارش: #{order_id}\n\n"
            f"⏳ اکانت شما در حال آماده‌سازی است.\n"
            f"پس از آماده شدن، به شما اطلاع داده خواهد شد."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        
        # اطلاع به ادمین‌ها
        self.notify_admins_payment(order_id)
    
    def show_my_orders(self, call):
        """نمایش سفارشات کاربر"""
        user_id = call.from_user.id
        
        # فیلتر سفارشات کاربر از pending_orders
        user_orders = [(order_id, order) for order_id, order in pending_orders.items() 
                    if order['user_id'] == user_id]
        
        if not user_orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="account_maker"))
            self.bot.edit_message_text(
                "📦 شما هنوز سفارشی ثبت نکردهاید.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "📦 **سفارشات ChatGPT GO شما:**\n\n"
        
        status_text = {
            'waiting_email': '📧 در انتظار ایمیل',
            'waiting_password': '🔐 در انتظار پسورد',
            'waiting_admin_approval': '⏳ در انتظار تایید ادمین',
            'preparing': '🔧 در حال آماده‌سازی',
            'delivered': '🎉 تحویل داده شده',
            'rejected': '❌ رد شده'
        }
        
        for order_id, order in user_orders[:5]:
            text += f"""🆔 سفارش: `{order_id}`
    📧 ایمیل: {order.get('email', 'N/A')}
    💰 قیمت: {CHATGPT_GO_PRODUCT['price']:,} تومان
    📊 وضعیت: {status_text.get(order['status'], order['status'])}
    📅 تاریخ: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}

    """
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="account_maker"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    # ===== ADMIN HANDLERS =====
    
    def admin_menu(self, call):
        """منوی ادمین Account Maker"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("➕ افزودن نوع اکانت", callback_data="admin_acc_add_type"),
            types.InlineKeyboardButton("📊 مدیریت انواع اکانت", callback_data="admin_acc_manage_types"),
            types.InlineKeyboardButton("⏳ سفارشات در انتظار", callback_data="admin_acc_pending_orders"),
            types.InlineKeyboardButton("📈 آمار", callback_data="admin_acc_statistics"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu")
        )
        
        self.bot.edit_message_text(
            "🛡️ **مدیریت اکانت‌های سفارشی**\n\nیکی از گزینه‌ها را انتخاب کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    def admin_add_type_start(self, call):
        """شروع افزودن نوع اکانت"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        set_state(call.from_user.id, "acc_admin_waiting_name")
        user_data[call.from_user.id] = {}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_account_maker"))
        
        self.bot.send_message(
            call.message.chat.id,
            "➕ **افزودن نوع اکانت جدید**\n\n📝 نام نوع اکانت را وارد کنید:\n(مثال: اکانت Netflix پرمیوم)",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def admin_manage_types(self, call):
        """مدیریت انواع اکانت"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            types_list = AccountMakerDB.get_all_account_types(conn)
        
        if not types_list:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
            
            self.bot.edit_message_text(
                "❌ هیچ نوع اکانتی یافت نشد.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for acc_type in types_list:
            status_emoji = "✅" if acc_type['is_active'] else "❌"
            button_text = f"{status_emoji} {acc_type['name']} - {acc_type['price']:,.0f}T"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f"admin_acctype_{acc_type['id']}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
        
        self.bot.edit_message_text(
            "📊 **مدیریت انواع اکانت**\n\nیک نوع اکانت را انتخاب کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    def admin_show_type(self, call):
        """نمایش جزئیات نوع اکانت برای ادمین"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        type_id = int(call.data.split("_")[2])
        
        with self.db.get_connection() as conn:
            acc_type = AccountMakerDB.get_account_type(conn, type_id)
        
        if not acc_type:
            self.bot.answer_callback_query(call.id, "❌ یافت نشد!", show_alert=True)
            return
        
        status = "✅ فعال" if acc_type['is_active'] else "❌ غیرفعال"
        toggle_text = "❌ غیرفعال کردن" if acc_type['is_active'] else "✅ فعال کردن"
        
        text = (
            f"🛡️ **{acc_type['name']}**\n\n"
            f"📝 توضیحات: {acc_type['description']}\n\n"
            f"📋 قوانین:\n{acc_type['rules']}\n\n"
            f"💰 قیمت: {acc_type['price']:,.0f} تومان\n"
            f"⏱ زمان تحویل: {acc_type['delivery_time_hours']} ساعت\n"
            f"🔔 وضعیت: {status}"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(toggle_text, callback_data=f"admin_acc_toggle_{type_id}"),
            types.InlineKeyboardButton("🗑 حذف", callback_data=f"admin_acc_delete_{type_id}")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_acc_manage_types"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_toggle_type(self, call):
        """تغییر وضعیت نوع اکانت"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        type_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            AccountMakerDB.toggle_account_type_status(conn, type_id)
        
        self.bot.answer_callback_query(call.id, "✅ وضعیت تغییر کرد", show_alert=True)
        
        call.data = f"admin_acctype_{type_id}"
        self.admin_show_type(call)
    
    def admin_delete_type(self, call):
        """حذف نوع اکانت"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        type_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            result = AccountMakerDB.delete_account_type(conn, type_id)
        
        if result.get("success"):
            self.bot.answer_callback_query(call.id, "✅ حذف شد!", show_alert=True)
            self.admin_manage_types(call)
        else:
            self.bot.answer_callback_query(call.id, f"❌ {result.get('error')}", show_alert=True)
    
    def admin_pending_orders(self, call):
        """نمایش سفارشات در انتظار"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            orders = AccountMakerDB.get_pending_orders(conn)
        
        if not orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
            
            self.bot.edit_message_text(
                "✅ سفارش در انتظاری وجود ندارد.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "⏳ **سفارشات در انتظار:**\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for order in orders:
            status_emoji = {'waiting_confirmation': '⏳', 'confirmed': '✅', 'paid': '💳'}.get(order['status'], '❓')
            button_text = f"{status_emoji} #{order['id']} - {order['account_type_name']} ({order['email'][:20]}...)"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f"admin_acc_order_{order['id']}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
        
        self.bot.edit_message_text(
            text + f"تعداد: {len(orders)} سفارش",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    def admin_show_order(self, call):
        """نمایش جزئیات سفارش برای ادمین"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        order_id = int(call.data.split("_")[3])
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            self.bot.answer_callback_query(call.id, "❌ یافت نشد!", show_alert=True)
            return
        
        status_text = {
            'waiting_confirmation': '⏳ در انتظار تایید',
            'confirmed': '✅ تایید شده',
            'paid': '💳 پرداخت شده',
            'delivered': '🎉 تحویل داده شده'
        }
        
        text = (
            f"🆔 **سفارش #{order_id}**\n\n"
            f"👤 کاربر: {order['user_id']}\n"
            f"🛡️ نوع اکانت: {order['account_type_name']}\n"
            f"📧 ایمیل: `{order['email']}`\n"
            f"🔐 پسورد: `{order['password']}`\n"
            f"💰 مبلغ: {order['price']:,.0f} تومان\n"
            f"📊 وضعیت: {status_text.get(order['status'], order['status'])}\n"
            f"💳 پرداخت: {'✅ انجام شده' if order['payment_status'] == 'paid' else '❌ نشده'}\n"
            f"📅 تاریخ: {order['created_at']}\n"
        )
        
        if order['account_info']:
            text += f"\n🎯 اطلاعات اکانت تحویلی:\n{order['account_info']}"
        
        markup = types.InlineKeyboardMarkup()
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_acc_approve_{order_id}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"admin_acc_reject_{order_id}")
        )
        if order['status'] == 'paid':
            markup.add(types.InlineKeyboardButton("✅ تحویل اکانت", callback_data=f"admin_acc_deliver_{order_id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_acc_pending_orders"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_deliver_order(self, call):
        """تحویل اکانت به کاربر"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        order_id = int(call.data.split("_")[3])
        
        set_state(call.from_user.id, f"acc_admin_deliver_{order_id}")
        user_data[call.from_user.id] = {'order_id': order_id}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"admin_acc_order_{order_id}"))
        
        self.bot.send_message(
            call.message.chat.id,
            f"✅ **تحویل سفارش #{order_id}**\n\n"
            f"اطلاعات اکانت آماده شده را وارد کنید:\n"
            f"(مثال: Username: xxx / Password: yyy / Link: zzz)",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def admin_statistics(self, call):
        """آمار اکانت‌های سفارشی"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            stats = AccountMakerDB.get_statistics(conn)
            types_count = len(AccountMakerDB.get_all_account_types(conn))
        
        text = (
            f"📈 **آمار اکانت‌های سفارشی**\n\n"
            f"🛡️ انواع اکانت: {types_count}\n"
            f"⏳ سفارشات در انتظار: {stats['pending_count']}\n"
            f"✅ سفارشات تحویل داده شده: {stats['delivered_count']}\n"
            f"💰 درآمد کل: {stats['total_revenue']:,.0f} تومان"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_acc_statistics"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_account_maker"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    # ===== HELPER METHODS =====
    
    def admin_approve_order(self, call):
        """تایید سفارش توسط ادمین"""
        from bot import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        order_id = call.data.replace('admin_acc_approve_', '')
        
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        order = pending_orders[order_id]
        
        if order['status'] != 'waiting_admin_approval':
            self.bot.answer_callback_query(call.id, "❌ این سفارش قبلاً پردازش شده!", show_alert=True)
            return
        
        # تغییر وضعیت به در حال آماده‌سازی
        order['status'] = 'preparing'
        order['approved_by'] = call.from_user.id
        order['approved_at'] = time.time()
        
        # به‌روزرسانی پیام ادمین
        updated_text = f"""✅ **سفارش تایید شد**

    📋 اطلاعات سفارش:
    • شناسه: `{order_id}`
    • User ID: `{order['user_id']}`
    • ایمیل: `{order['email']}`

    ✅ تایید شده توسط: {call.from_user.first_name}
    🕐 زمان تایید: {time.strftime('%H:%M:%S')}

    **مرحله بعد:** لطفاً اطلاعات اکانت را ارسال کنید."""
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "📤 ارسال اطلاعات اکانت", 
            callback_data=f'admin_acc_send_{order_id}'
        ))
        
        try:
            self.bot.edit_message_text(
                updated_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        except:
            pass
        
        # اطلاع‌رسانی به کاربر
        self.bot.send_message(
            order['user_id'],
            f"""✅ **سفارش شما تایید شد!**

    شناسه سفارش: `{order_id}`

    ⏳ **مرحله 5 از 6: در حال آماده‌سازی اکانت**

    لطفاً منتظر بمانید تا حساب شما آماده شود.
    این فرآیند حداکثر {CHATGPT_GO_PRODUCT['delivery_time']} ساعت طول می‌کشد.

    ✅ به محض آماده شدن، اطلاعات اکانت برای شما ارسال خواهد شد."""
        )
        
        self.bot.answer_callback_query(call.id, "✅ سفارش تایید شد!", show_alert=True)

    def admin_reject_order(self, call):
        """رد سفارش توسط ادمین"""
        from bot import is_admin
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        order_id = call.data.replace('admin_acc_reject_', '')
        
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        order = pending_orders[order_id]
        
        if order['status'] != 'waiting_admin_approval':
            self.bot.answer_callback_query(call.id, "❌ این سفارش قبلاً پردازش شده!", show_alert=True)
            return
        
        # تغییر وضعیت به رد شده
        order['status'] = 'rejected'
        order['rejected_by'] = call.from_user.id
        order['rejected_at'] = time.time()
        
        # به‌روزرسانی پیام ادمین
        updated_text = f"""❌ **سفارش رد شد**

    📋 اطلاعات سفارش:
    • شناسه: `{order_id}`
    • User ID: `{order['user_id']}`

    ❌ رد شده توسط: {call.from_user.first_name}"""
        
        try:
            self.bot.edit_message_text(
                updated_text,
                call.message.chat.id,
                call.message.message_id
            )
        except:
            pass
        
        # اطلاع‌رسانی به کاربر
        self.bot.send_message(
            order['user_id'],
            f"""❌ **متأسفانه سفارش شما رد شد**

    شناسه سفارش: `{order_id}`

    دلیل: اطلاعات ارسالی معتبر نبود یا ایمیل قبلاً در OpenAI ثبت شده است.

    💬 برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."""
        )
        
        self.bot.answer_callback_query(call.id, "❌ سفارش رد شد!", show_alert=True)

    def admin_deliver_order(self, call):
        """درخواست ارسال اطلاعات اکانت از ادمین"""
        from bot import is_admin, set_state, user_data
        if not is_admin(call.from_user.id):
            return
        
        order_id = call.data.replace('admin_acc_send_', '')
        
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        
        # ذخیره order_id برای ادمین
        user_data[call.from_user.id] = {'admin_delivering_order': order_id}
        set_state(call.from_user.id, 'admin_sending_account_info')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data='admin_menu'))
        
        self.bot.send_message(
            call.message.chat.id,
            f"""📤 **ارسال اطلاعات اکانت**

    شناسه سفارش: `{order_id}`

    لطفاً اطلاعات اکانت را به فرمت زیر ارسال کنید:
    Username: example@email.com
    Password: your_password_here
    Link: https://chat.openai.com

    یا هر فرمت دلخواه دیگری که اطلاعات کامل را شامل شود.""",
            reply_markup=markup
        )
        
        self.bot.delete_message(call.message.chat.id, call.message.message_id)

    def admin_pending_orders(self, call):
        """نمایش سفارشات در انتظار"""
        from bot import is_admin
        if not is_admin(call.from_user.id):
            return
        
        # فیلتر سفارشات در انتظار
        orders = [order for order_id, order in pending_orders.items() 
                if order['status'] in ['waiting_admin_approval', 'preparing']]
        
        if not orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
            self.bot.edit_message_text(
                "✅ سفارش در انتظاری وجود ندارد.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "⏳ **سفارشات در انتظار:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for order_id, order in list(pending_orders.items())[:10]:
            if order['status'] in ['waiting_admin_approval', 'preparing']:
                status_emoji = {'waiting_admin_approval': '⏳', 'preparing': '🔧'}.get(order['status'], '❓')
                button_text = f"{status_emoji} {order_id} - {order.get('email', 'N/A')[:20]}..."
                markup.add(types.InlineKeyboardButton(button_text, callback_data=f'admin_acc_order_{order_id}'))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu"))
        
        self.bot.edit_message_text(
            text + f"تعداد: {len(orders)} سفارش",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    def admin_show_order(self, call):
        """نمایش جزئیات سفارش برای ادمین"""
        from bot import is_admin
        if not is_admin(call.from_user.id):
            return
        
        order_id = call.data.replace('admin_acc_order_', '')
        
        if order_id not in pending_orders:
            self.bot.answer_callback_query(call.id, "❌ یافت نشد!", show_alert=True)
            return
        
        order = pending_orders[order_id]
        
        status_text = {
            'waiting_admin_approval': '⏳ در انتظار تایید',
            'preparing': '🔧 در حال آماده‌سازی',
            'delivered': '✅ تحویل داده شده',
            'rejected': '❌ رد شده'
        }
        
        text = f"""🆔 **سفارش {order_id}**

    👤 کاربر: {order['user_id']}
    🛡️ نوع اکانت: ChatGPT GO
    📧 ایمیل: `{order.get('email', 'N/A')}`
    🔐 پسورد: `{order.get('password', 'N/A')}`
    💰 مبلغ: {CHATGPT_GO_PRODUCT['price']:,} تومان
    📊 وضعیت: {status_text.get(order['status'], order['status'])}
    📅 تاریخ: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}"""
        
        if order.get('account_info'):
            text += f"\n\n🎯 اطلاعات اکانت تحویلی:\n{order['account_info']}"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        if order['status'] == 'waiting_admin_approval':
            markup.row(
                types.InlineKeyboardButton("✅ تایید", callback_data=f'admin_acc_approve_{order_id}'),
                types.InlineKeyboardButton("❌ رد", callback_data=f'admin_acc_reject_{order_id}')
            )
        elif order['status'] == 'preparing':
            markup.add(types.InlineKeyboardButton("📤 ارسال اکانت", callback_data=f'admin_acc_send_{order_id}'))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_acc_pending_orders"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

        
    def notify_admins_new_order(self, order_id: int):
        """اطلاع به ادمین‌ها - سفارش جدید"""
        from config import config
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"🔔 **سفارش جدید اکانت سفارشی!**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"👤 کاربر: {order['user_id']}\n"
            f"🛡️ نوع: {order['account_type_name']}\n"
            f"📧 ایمیل: {order['email']}\n"
            f"🔐 پسورد: {order['password']}\n"
            f"💰 مبلغ: {order['price']:,.0f} تومان\n"
            f"📊 وضعیت: منتظر پرداخت"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👁 مشاهده سفارش", callback_data=f"admin_acc_order_{order_id}"))
        
        for admin_id in config.admin_list:
            try:
                self.bot.send_message(admin_id, text, reply_markup=markup)
            except:
                pass
    
    def notify_admins_payment(self, order_id: int):
        """اطلاع به ادمین‌ها - پرداخت انجام شد"""
        from config import config
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"💳 **پرداخت انجام شد!**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"👤 کاربر: {order['user_id']}\n"
            f"🛡️ نوع: {order['account_type_name']}\n"
            f"📧 ایمیل: {order['email']}\n"
            f"🔐 پسورد: {order['password']}\n"
            f"💰 مبلغ: {order['price']:,.0f} تومان\n"
            f"⏰ زمان تحویل: {order['delivery_time_hours']} ساعت\n\n"
            f"⚠️ منتظر آماده‌سازی اکانت است!"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تحویل اکانت", callback_data=f"admin_acc_deliver_{order_id}"))
        
        for admin_id in config.admin_list:
            try:
                self.bot.send_message(admin_id, text, reply_markup=markup)
            except:
                pass
    
    def notify_user_delivered(self, order_id: int):
        """اطلاع به کاربر - اکانت آماده است"""
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"🎉 **اکانت شما آماده است!**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"🛡️ نوع: {order['account_type_name']}\n\n"
            f"🎯 **اطلاعات اکانت:**\n{order['account_info']}\n\n"
            f"✅ از خرید شما متشکریم!"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
        
        try:
            self.bot.send_message(order['user_id'], text, reply_markup=markup)
        except:
            pass

    def notify_admins_for_approval(self, order_id: int):
        """اطلاع به ادمین‌ها برای تایید سفارش"""
        from config import config
        
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"🔔 **درخواست جدید اکانت سفارشی!**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"👤 کاربر: `{order['user_id']}`\n"
            f"🎮 نوع: {order['account_type_name']}\n"
            f"📧 ایمیل: `{order['email']}`\n"
            f"🔐 پسورد: `{order['password']}`\n"
            f"💰 مبلغ: {order['price']:,.0f} تومان\n\n"
            f"⚠️ این درخواست نیاز به تایید شما دارد."
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_acc_approve_{order_id}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"admin_acc_reject_{order_id}")
        )
        markup.add(types.InlineKeyboardButton("👁 مشاهده جزئیات", callback_data=f"admin_acc_order_{order_id}"))
        
        for admin_id in config.admin_list:
            try:
                self.bot.send_message(admin_id, text, reply_markup=markup)
            except Exception as e:
                logger.error(f"خطا در ارسال به ادمین {admin_id}: {e}")


    def notify_user_approved(self, order_id: int):
        """اطلاع به کاربر - ادمین تایید کرد"""
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"✅ **درخواست شما تایید شد!**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"🎮 نوع: {order['account_type_name']}\n\n"
            f"📧 **مرحله 3 از 5: تایید ایمیل**\n\n"
            f"⚠️ لطفاً به ایمیل خود (`{order['email']}`) مراجعه کرده و ایمیل تأیید را تأیید کنید.\n\n"
            f"⚠️ توجه مهم: تأیید این مرحله تنها پس از موفقیت‌آمیز بودن ساخت اکانت مجاز است؛ در غیر این صورت، سفارش شما حذف خواهد شد.\n\n"
            f"پس از تأیید ایمیل، دکمه زیر را بزنید:"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ ایمیل را تأیید کردم", callback_data=f"acc_confirm_email_{order_id}"))
        markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
        
        try:
            self.bot.send_message(order['user_id'], text, reply_markup=markup)
        except Exception as e:
            logger.error(f"خطا در ارسال به کاربر {order['user_id']}: {e}")

    def notify_user_rejected(self, order_id: int):
        """اطلاع به کاربر - ادمین رد کرد"""
        with self.db.get_connection() as conn:
            order = AccountMakerDB.get_order(conn, order_id)
        
        if not order:
            return
        
        text = (
            f"❌ **متأسفانه درخواست شما رد شد**\n\n"
            f"🆔 سفارش: #{order_id}\n"
            f"🎮 نوع: {order['account_type_name']}\n\n"
            f"برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.\n\n"
            f"می‌توانید دوباره تلاش کنید."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 تلاش مجدد", callback_data="account_maker"),
            types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support")
        )
        
        try:
            self.bot.send_message(order['user_id'], text, reply_markup=markup)
        except Exception as e:
            logger.error(f"خطا در ارسال به کاربر {order['user_id']}: {e}")

# ===== MESSAGE HANDLERS برای State Management =====
def handle_account_maker_states(bot, db, message, user_id, state, user_data):
    """مدیریت state های Account Maker"""
    
    # دریافت ایمیل
    if state == 'chatgpt_go_waiting_email':
        email = message.text.strip()
        order_id = user_data[user_id]['order_id']
        
        pending_orders[order_id]['email'] = email
        pending_orders[order_id]['status'] = 'waiting_password'
        
        from bot import set_state
        set_state(user_id, 'chatgpt_go_waiting_password')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data='account_maker'))
        
        bot.send_message(
            message.chat.id,
            f"""🔐 **مرحله 3 از 6: ارسال پسورد ایمیل**

ایمیل دریافت شد: `{email}`

حالا لطفاً پسورد ایمیل خود را ارسال کنید:""",
            reply_markup=markup
        )
        return True
    
    # دریافت پسورد
    elif state == 'chatgpt_go_waiting_password':
        password = message.text.strip()
        order_id = user_data[user_id]['order_id']
        
        pending_orders[order_id]['password'] = password
        pending_orders[order_id]['status'] = 'waiting_admin_approval'
        
        order_info = pending_orders[order_id]
        
        # پیام تایید برای کاربر
        bot.send_message(
            message.chat.id,
            f"""⏳ **مرحله 4 از 6: منتظر تایید ادمین باشید**

اطلاعات شما با موفقیت ثبت شد:
• شناسه سفارش: `{order_id}`
• ایمیل: `{order_info['email']}`

⏰ لطفاً منتظر تایید ادمین باشید. این عملیات معمولاً کمتر از 1 ساعت طول می‌کشد.

⚠️ اگر سفارش شما بیشتر از 1 ساعت تایید نشود، به صورت خودکار لغو خواهد شد."""
        )
        
        # ارسال پیام به ادمین‌ها برای تایید
        send_admin_approval_request(bot, order_id)
        
        from bot import clear_state
        clear_state(user_id)
        return True
    
    # دریافت اطلاعات اکانت از ادمین
    elif state == 'admin_sending_account_info':
        account_info = message.text.strip()
        order_id = user_data[user_id]['admin_delivering_order']
        
        if order_id not in pending_orders:
            bot.send_message(message.chat.id, "❌ خطا: سفارش یافت نشد!")
            from bot import clear_state
            clear_state(user_id)
            return True
        
        order = pending_orders[order_id]
        
        # ذخیره اطلاعات اکانت
        order['account_info'] = account_info
        order['status'] = 'delivered'
        order['delivered_at'] = time.time()
        
        # ارسال اطلاعات به کاربر
        customer_message = f"""🎉 **اکانت شما آماده است!**

شناسه سفارش: `{order_id}`
محصول: **{CHATGPT_GO_PRODUCT['name']}**

📋 **اطلاعات اکانت:**
{account_info}

⚠️ **یادآوری قوانین:**
• از VPN معتبر استفاده کنید
• استفاده همزمان چند نفره ممکن است حساب را مسدود کند
• پشتیبانی فقط در هفته اول و در صورت غیرفعال شدن حساب

✅ از خرید شما متشکریم!"""
        
        bot.send_message(order['user_id'], customer_message)
        
        # تأیید برای ادمین
        bot.send_message(
            message.chat.id,
            f"""✅ **اطلاعات با موفقیت ارسال شد!**

شناسه سفارش: `{order_id}`
کاربر: `{order['user_id']}`

✅ سفارش تکمیل شد."""
        )
        
        from bot import clear_state
        clear_state(user_id)
        return True
    
    return False

# تابع کمکی برای ارسال درخواست تایید به ادمین
def send_admin_approval_request(bot, order_id):
    from config import config
    
    order = pending_orders[order_id]
    
    text = f"""🔔 **درخواست جدید: ChatGPT GO**

📋 اطلاعات سفارش:
• شناسه: `{order_id}`
• نام کاربر: @{order.get('username', 'ناشناس')}
• User ID: `{order['user_id']}`
• محصول: {order['product']}
• ایمیل: `{order['email']}`
• پسورد: `{order['password']}`
• قیمت: {CHATGPT_GO_PRODUCT['price']:,} تومان

⏰ زمان ثبت: {time.strftime('%Y-%m-%d %H:%M', time.localtime(order['created_at']))}"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ تایید", callback_data=f'admin_acc_approve_{order_id}'),
        types.InlineKeyboardButton("❌ رد", callback_data=f'admin_acc_reject_{order_id}')
    )
    
    for admin_id in config.admin_list:
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
        except:
            pass
