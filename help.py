"""
ماژول پشتیبانی و ارتباط کاربر-ادمین
کاربر می‌تواند در هر ساعت حداکثر 5 پیام بفرستد
ادمین محدودیت ندارد
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from telebot import types
import time

logger = logging.getLogger(__name__)

# ===== DATABASE METHODS =====

class HelpDB:
    """متدهای دیتابیس برای سیستم پشتیبانی"""
    
    @staticmethod
    def init_tables(conn):
        """ایجاد جداول مورد نیاز"""
        
        # جدول پیام‌های پشتیبانی
        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                admin_id INTEGER,
                message_text TEXT NOT NULL,
                is_from_admin BOOLEAN DEFAULT 0,
                is_read BOOLEAN DEFAULT 0,
                parent_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_message_id) REFERENCES support_messages(id)
            )
        """)
        
        # جدول محدودیت پیام (rate limiting)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_rate_limit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_count INTEGER DEFAULT 1,
                last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        """)
        
        # جدول تیکت‌های باز
        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                status TEXT DEFAULT 'open',
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        logger.info("✅ جداول سیستم پشتیبانی ایجاد شد")
    
    @staticmethod
    def check_rate_limit(conn, user_id: int, limit: int = 5, increment: bool = True) -> Dict:
        """بررسی محدودیت تعداد پیام"""
        cursor = conn.execute("""
            SELECT message_count, last_reset 
            FROM message_rate_limit 
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        current_time = datetime.now()
        
        if not row:
            # اولین پیام کاربر
            if increment:
                conn.execute("""
                    INSERT INTO message_rate_limit (user_id, message_count, last_reset)
                    VALUES (?, 1, ?)
                """, (user_id, current_time.isoformat()))
                return {"allowed": True, "remaining": limit - 1}
            else:
                # فقط چک می‌کنیم، شمارنده را افزایش نمی‌دهیم
                return {"allowed": True, "remaining": limit}
        
        message_count, last_reset_str = row
        last_reset = datetime.fromisoformat(last_reset_str)
        
        # بررسی یک ساعت گذشته
        if current_time - last_reset > timedelta(hours=1):
            # ریست کردن شمارنده
            if increment:
                conn.execute("""
                    UPDATE message_rate_limit 
                    SET message_count = 1, last_reset = ?
                    WHERE user_id = ?
                """, (current_time.isoformat(), user_id))
                return {"allowed": True, "remaining": limit - 1}
            else:
                # فقط چک می‌کنیم
                return {"allowed": True, "remaining": limit}
        
        # در همان ساعت
        if message_count >= limit:
            time_left = timedelta(hours=1) - (current_time - last_reset)
            minutes_left = int(time_left.total_seconds() / 60)
            return {
                "allowed": False, 
                "remaining": 0,
                "minutes_left": minutes_left
            }
        
        # افزایش شمارنده (فقط اگر increment=True باشد)
        if increment:
            conn.execute("""
                UPDATE message_rate_limit 
                SET message_count = message_count + 1
                WHERE user_id = ?
            """, (user_id,))
            return {"allowed": True, "remaining": limit - message_count - 1}
        else:
            # فقط چک می‌کنیم، افزایش نمی‌دهیم
            return {"allowed": True, "remaining": limit - message_count}

    @staticmethod
    def save_message(conn, user_id: int, message_text: str, is_from_admin: bool = False, 
                    admin_id: int = None, parent_message_id: int = None):
        """ذخیره پیام"""
        cursor = conn.execute("""
            INSERT INTO support_messages 
            (user_id, admin_id, message_text, is_from_admin, parent_message_id)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, admin_id, message_text, is_from_admin, parent_message_id))
        
        # به‌روزرسانی تیکت
        conn.execute("""
            INSERT OR REPLACE INTO support_tickets (user_id, status, last_message_at)
            VALUES (?, 'open', ?)
        """, (user_id, datetime.now().isoformat()))
        
        return cursor.lastrowid
    
    @staticmethod
    def get_user_messages(conn, user_id: int, limit: int = 20):
        """دریافت پیام‌های کاربر"""
        cursor = conn.execute("""
            SELECT * FROM support_messages
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def get_unread_messages_count(conn, user_id: int, for_admin: bool = False):
        """تعداد پیام‌های خوانده نشده"""
        if for_admin:
            # پیام‌های کاربران که ادمین نخوانده
            cursor = conn.execute("""
                SELECT COUNT(*) FROM support_messages
                WHERE is_from_admin = 0 AND is_read = 0
            """)
        else:
            # پیام‌های ادمین که کاربر نخوانده
            cursor = conn.execute("""
                SELECT COUNT(*) FROM support_messages
                WHERE user_id = ? AND is_from_admin = 1 AND is_read = 0
            """, (user_id,))
        
        return cursor.fetchone()[0]
    
    @staticmethod
    def mark_messages_as_read(conn, user_id: int, is_from_admin: bool):
        """علامت‌گذاری پیام‌ها به عنوان خوانده شده"""
        if is_from_admin:
            # ادمین می‌خواند - پیام‌های کاربر را خوانده کن
            conn.execute("""
                UPDATE support_messages
                SET is_read = 1
                WHERE user_id = ? AND is_from_admin = 0 AND is_read = 0
            """, (user_id,))
        else:
            # کاربر می‌خواند - پیام‌های ادمین را خوانده کن
            conn.execute("""
                UPDATE support_messages
                SET is_read = 1
                WHERE user_id = ? AND is_from_admin = 1 AND is_read = 0
            """, (user_id,))
    
    @staticmethod
    def get_open_tickets(conn):
        """دریافت تیکت‌های باز"""
        cursor = conn.execute("""
            SELECT t.*, 
                   (SELECT COUNT(*) FROM support_messages 
                    WHERE user_id = t.user_id AND is_read = 0 AND is_from_admin = 0) as unread_count,
                   (SELECT message_text FROM support_messages 
                    WHERE user_id = t.user_id 
                    ORDER BY created_at DESC LIMIT 1) as last_message
            FROM support_tickets t
            WHERE status = 'open'
            ORDER BY last_message_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def close_ticket(conn, user_id: int):
        """بستن تیکت"""
        conn.execute("""
            UPDATE support_tickets
            SET status = 'closed'
            WHERE user_id = ?
        """, (user_id,))
    
    @staticmethod
    def get_statistics(conn):
        """آمار سیستم پشتیبانی"""
        cursor = conn.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'open'")
        open_tickets = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM support_messages WHERE is_from_admin = 0")
        total_user_messages = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM support_messages WHERE is_from_admin = 1")
        total_admin_messages = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM support_messages WHERE is_read = 0 AND is_from_admin = 0")
        unread_messages = cursor.fetchone()[0]
        
        return {
            "open_tickets": open_tickets,
            "total_user_messages": total_user_messages,
            "total_admin_messages": total_admin_messages,
            "unread_messages": unread_messages
        }


# ===== HANDLERS =====

class HelpHandlers:
    """handlers برای سیستم پشتیبانی"""
    
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    def register_handlers(self):
        """ثبت handlers"""
        
        # دستور /help برای کاربران
        self.bot.message_handler(commands=['help'])(self.cmd_help)
        
        # دستور /tickets برای ادمین
        self.bot.message_handler(commands=['tickets'])(self.cmd_tickets)
        
        # دستور /sendto برای ادمین
        self.bot.message_handler(commands=['sendto'])(self.cmd_sendto)
        
        # دستور /closeticket برای ادمین
        self.bot.message_handler(commands=['closeticket'])(self.cmd_closeticket)
        
        # Callback handlers
        self.bot.callback_query_handler(func=lambda c: c.data == "help_support")(self.show_support)
        self.bot.callback_query_handler(func=lambda c: c.data == "help_view_messages")(self.view_messages)
        self.bot.callback_query_handler(func=lambda c: c.data == "help_send_message")(self.start_send_message)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_support_panel")(self.admin_support_panel)
        self.bot.callback_query_handler(func=lambda c: c.data == "admin_view_tickets")(self.admin_view_tickets)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_ticket_"))(self.admin_view_ticket)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_reply_"))(self.admin_start_reply)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith("admin_close_"))(self.admin_close_ticket)
    
    # ===== USER HANDLERS =====
    
    def cmd_help(self, message):
        """دستور /help"""
        user_id = message.from_user.id
        
        with self.db.get_connection() as conn:
            unread_count = HelpDB.get_unread_messages_count(conn, user_id, for_admin=False)
        
        text = (
            f"💬 **پشتیبانی و راهنما**\n\n"
            f"از این بخش می‌توانید با پشتیبانی ارتباط برقرار کنید.\n\n"
        )
        
        if unread_count > 0:
            text += f"🔴 شما {unread_count} پیام خوانده نشده دارید!\n\n"
        
        text += (
            f"⚠️ **محدودیت:** شما می‌توانید در هر ساعت حداکثر 5 پیام ارسال کنید.\n\n"
            f"📋 از دکمه‌های زیر استفاده کنید:"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("✉️ ارسال پیام", callback_data="help_send_message"),
            types.InlineKeyboardButton(f"📬 پیام‌های من ({unread_count} خوانده نشده)", callback_data="help_view_messages"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
        )
        
        self.bot.send_message(message.chat.id, text, reply_markup=markup)
    
    def show_support(self, call):
        """نمایش پشتیبانی"""
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            unread_count = HelpDB.get_unread_messages_count(conn, user_id, for_admin=False)
        
        text = (
            f"💬 **پشتیبانی و راهنما**\n\n"
            f"از این بخش می‌توانید با پشتیبانی ارتباط برقرار کنید.\n\n"
        )
        
        if unread_count > 0:
            text += f"🔴 شما {unread_count} پیام خوانده نشده دارید!\n\n"
        
        text += (
            f"⚠️ **محدودیت:** شما می‌توانید در هر ساعت حداکثر 5 پیام ارسال کنید.\n\n"
            f"📋 از دکمه‌های زیر استفاده کنید:"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("✉️ ارسال پیام", callback_data="help_send_message"),
            types.InlineKeyboardButton(f"📬 پیام‌های من ({unread_count} خوانده نشده)", callback_data="help_view_messages"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def view_messages(self, call):
        """نمایش پیام‌های کاربر"""
        user_id = call.from_user.id
        
        with self.db.get_connection() as conn:
            messages = HelpDB.get_user_messages(conn, user_id, limit=10)
            HelpDB.mark_messages_as_read(conn, user_id, is_from_admin=False)
        
        if not messages:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="help_support"))
            
            self.bot.edit_message_text(
                "📭 شما هنوز پیامی ندارید.\n\nبرای ارسال پیام از دکمه 'ارسال پیام' استفاده کنید.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "📬 **پیام‌های شما:**\n\n"
        
        for msg in reversed(messages[-10:]):
            sender = "🔵 شما" if not msg['is_from_admin'] else "🟢 پشتیبانی"
            created_at = msg['created_at'].split('.')[0] if '.' in msg['created_at'] else msg['created_at']
            text += f"{sender} ({created_at}):\n{msg['message_text']}\n\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✉️ ارسال پیام", callback_data="help_send_message"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="help_support")
        )
        
        self.bot.edit_message_text(text[:4000], call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def start_send_message(self, call):
        """شروع ارسال پیام"""
        user_id = call.from_user.id
        
        # بررسی محدودیت (بدون افزایش شمارنده)
        with self.db.get_connection() as conn:
            rate_check = HelpDB.check_rate_limit(conn, user_id, increment=False)  # ✅ تغییر اینجا
        
        if not rate_check['allowed']:
            self.bot.answer_callback_query(
                call.id,
                f"⚠️ شما به حد مجاز رسیده‌اید!\n\n"
                f"لطفاً {rate_check['minutes_left']} دقیقه دیگر تلاش کنید.",
                show_alert=True
            )
            return
        
        # تنظیم state
        from bot import set_state, user_data
        set_state(user_id, "help_waiting_message")
        user_data[user_id] = {'remaining': rate_check['remaining']}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="help_support"))
        
        self.bot.send_message(
            call.message.chat.id,
            f"✉️ **ارسال پیام به پشتیبانی**\n\n"
            f"پیام خود را تایپ کرده و ارسال کنید.\n\n"
            f"📊 شما می‌توانید {rate_check['remaining']} پیام دیگر ارسال کنید.",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)

    # ===== ADMIN HANDLERS =====
    
    def cmd_tickets(self, message):
        """دستور /tickets - مشاهده تیکت‌ها"""
        from bot import is_admin
        
        if not is_admin(message.from_user.id):
            self.bot.send_message(message.chat.id, "❌ شما دسترسی ندارید!")
            return
        
        with self.db.get_connection() as conn:
            tickets = HelpDB.get_open_tickets(conn)
        
        if not tickets:
            self.bot.send_message(message.chat.id, "✅ تیکت بازی وجود ندارد!")
            return
        
        text = "🎫 **تیکت‌های باز:**\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for ticket in tickets:
            unread = f"🔴 {ticket['unread_count']}" if ticket['unread_count'] > 0 else "✅"
            last_msg = ticket['last_message'][:30] + "..." if len(ticket['last_message']) > 30 else ticket['last_message']
            
            button_text = f"{unread} کاربر {ticket['user_id']}: {last_msg}"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f"admin_ticket_{ticket['user_id']}"))
        
        markup.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_view_tickets"))
        
        self.bot.send_message(message.chat.id, text, reply_markup=markup)
    
    def cmd_sendto(self, message):
        """دستور /sendto <user_id> <message> - ارسال پیام به کاربر"""
        from bot import is_admin
        
        if not is_admin(message.from_user.id):
            self.bot.send_message(message.chat.id, "❌ شما دسترسی ندارید!")
            return
        
        parts = message.text.split(maxsplit=2)
        
        if len(parts) < 3:
            self.bot.send_message(
                message.chat.id,
                "❌ فرمت صحیح:\n`/sendto <user_id> <message>`\n\nمثال:\n`/sendto 123456789 سلام، چطور می‌تونم کمکتون کنم?`"
            )
            return
        
        try:
            target_user_id = int(parts[1])
            message_text = parts[2]
            
            # ذخیره پیام
            with self.db.get_connection() as conn:
                HelpDB.save_message(
                    conn, 
                    user_id=target_user_id, 
                    message_text=message_text,
                    is_from_admin=True,
                    admin_id=message.from_user.id
                )
            
            # ارسال به کاربر
            try:
                self.bot.send_message(
                    target_user_id,
                    f"🟢 **پیام از پشتیبانی:**\n\n{message_text}\n\n"
                    f"برای پاسخ، دستور /help را بزنید."
                )
                self.bot.send_message(message.chat.id, f"✅ پیام به کاربر {target_user_id} ارسال شد!")
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ خطا در ارسال: {e}")
        
        except ValueError:
            self.bot.send_message(message.chat.id, "❌ user_id باید عدد باشد!")
    
    def cmd_closeticket(self, message):
        """دستور /closeticket <user_id> - بستن تیکت"""
        from bot import is_admin
        
        if not is_admin(message.from_user.id):
            self.bot.send_message(message.chat.id, "❌ شما دسترسی ندارید!")
            return
        
        parts = message.text.split()
        
        if len(parts) < 2:
            self.bot.send_message(message.chat.id, "❌ فرمت صحیح: `/closeticket <user_id>`")
            return
        
        try:
            target_user_id = int(parts[1])
            
            with self.db.get_connection() as conn:
                HelpDB.close_ticket(conn, target_user_id)
            
            self.bot.send_message(message.chat.id, f"✅ تیکت کاربر {target_user_id} بسته شد!")
            
            # اطلاع به کاربر
            try:
                self.bot.send_message(
                    target_user_id,
                    "✅ تیکت شما بسته شد.\n\nدر صورت نیاز، می‌توانید تیکت جدید باز کنید."
                )
            except:
                pass
        
        except ValueError:
            self.bot.send_message(message.chat.id, "❌ user_id باید عدد باشد!")
    
    def admin_support_panel(self, call):
        """پنل پشتیبانی ادمین"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ دسترسی غیرمجاز!", show_alert=True)
            return
        
        with self.db.get_connection() as conn:
            stats = HelpDB.get_statistics(conn)
        
        text = (
            f"🎫 **پنل پشتیبانی**\n\n"
            f"📊 تیکت‌های باز: {stats['open_tickets']}\n"
            f"🔴 پیام‌های خوانده نشده: {stats['unread_messages']}\n"
            f"📨 کل پیام‌های کاربران: {stats['total_user_messages']}\n"
            f"📤 کل پاسخ‌های ادمین: {stats['total_admin_messages']}"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🎫 تیکت‌های باز ({stats['open_tickets']})", callback_data="admin_view_tickets"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_menu")
        )
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_view_tickets(self, call):
        """نمایش تیکت‌های باز"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        with self.db.get_connection() as conn:
            tickets = HelpDB.get_open_tickets(conn)
        
        if not tickets:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_support_panel"))
            
            self.bot.edit_message_text(
                "✅ تیکت بازی وجود ندارد!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        text = "🎫 **تیکت‌های باز:**\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for ticket in tickets:
            unread = f"🔴 {ticket['unread_count']}" if ticket['unread_count'] > 0 else "✅"
            last_msg = ticket['last_message'][:30] + "..." if ticket['last_message'] and len(ticket['last_message']) > 30 else (ticket['last_message'] or "")
            
            button_text = f"{unread} کاربر {ticket['user_id']}: {last_msg}"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f"admin_ticket_{ticket['user_id']}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_support_panel"))
        
        self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_view_ticket(self, call):
        """نمایش جزئیات تیکت"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = int(call.data.split("_")[2])
        
        with self.db.get_connection() as conn:
            messages = HelpDB.get_user_messages(conn, user_id, limit=15)
            HelpDB.mark_messages_as_read(conn, user_id, is_from_admin=True)
        
        if not messages:
            self.bot.answer_callback_query(call.id, "❌ پیامی یافت نشد!", show_alert=True)
            return
        
        text = f"💬 **گفتگو با کاربر {user_id}:**\n\n"
        
        for msg in reversed(messages[-15:]):
            sender = "🔵 کاربر" if not msg['is_from_admin'] else "🟢 پشتیبانی"
            created_at = msg['created_at'].split('.')[0] if '.' in msg['created_at'] else msg['created_at']
            text += f"{sender} ({created_at}):\n{msg['message_text']}\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("💬 پاسخ", callback_data=f"admin_reply_{user_id}"),
            types.InlineKeyboardButton("✅ بستن تیکت", callback_data=f"admin_close_{user_id}")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_view_tickets"))
        
        self.bot.edit_message_text(text[:4000], call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    def admin_start_reply(self, call):
        """شروع پاسخ ادمین"""
        from bot import is_admin, set_state, user_data
        
        if not is_admin(call.from_user.id):
            return
        
        target_user_id = int(call.data.split("_")[2])
        
        set_state(call.from_user.id, f"help_admin_reply_{target_user_id}")
        user_data[call.from_user.id] = {'target_user_id': target_user_id}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"admin_ticket_{target_user_id}"))
        
        self.bot.send_message(
            call.message.chat.id,
            f"💬 **پاسخ به کاربر {target_user_id}**\n\nپیام خود را تایپ کنید:",
            reply_markup=markup
        )
        self.bot.delete_message(call.message.chat.id, call.message.message_id)
    
    def admin_close_ticket(self, call):
        """بستن تیکت"""
        from bot import is_admin
        
        if not is_admin(call.from_user.id):
            return
        
        user_id = int(call.data.split("_")[2])
        
        with self.db.get_connection() as conn:
            HelpDB.close_ticket(conn, user_id)
        
        self.bot.answer_callback_query(call.id, "✅ تیکت بسته شد!", show_alert=True)
        
        # اطلاع به کاربر
        try:
            self.bot.send_message(
                user_id,
                "✅ تیکت شما بسته شد.\n\nدر صورت نیاز، می‌توانید تیکت جدید باز کنید."
            )
        except:
            pass
        
        # بازگشت به لیست تیکت‌ها
        call.data = "admin_view_tickets"
        self.admin_view_tickets(call)


# ===== MESSAGE HANDLERS برای State Management =====

def handle_help_states(bot, db, message, user_id, state, user_data):
    """مدیریت state های سیستم پشتیبانی"""
    
    # کاربر در حال ارسال پیام
    if state == "help_waiting_message":
        message_text = message.text
        
        # بررسی محدودیت (با افزایش شمارنده)
        with db.get_connection() as conn:
            rate_check = HelpDB.check_rate_limit(conn, user_id, increment=True)  # ✅ تغییر اینجا
            
            if not rate_check['allowed']:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ شما به حد مجاز رسیده‌اید!\n\n"
                    f"لطفاً {rate_check['minutes_left']} دقیقه دیگر تلاش کنید."
                )
                from bot import clear_state
                clear_state(user_id)
                return True
            
            # ذخیره پیام
            HelpDB.save_message(conn, user_id, message_text, is_from_admin=False)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
        
        bot.send_message(
            message.chat.id,
            f"✅ پیام شما ارسال شد!\n\n"
            f"📊 شما می‌توانید {rate_check['remaining']} پیام دیگر ارسال کنید.\n\n"
            f"پشتیبانی به زودی پاسخ خواهد داد.",
            reply_markup=markup
        )
        
        # اطلاع به ادمین‌ها
        handlers = HelpHandlers(bot, db)
        handlers.notify_admins_new_message(user_id, message_text)
        
        from bot import clear_state
        clear_state(user_id)
        return True
    
    # ... بقیه کد

# ===== HELPER METHODS =====

def notify_admins_new_message_helper(bot, db, user_id: int, message_text: str):
    """اطلاع به ادمین‌ها - پیام جدید"""
    from config import config
    
    preview = message_text[:50] + "..." if len(message_text) > 50 else message_text
    
    text = (
        f"🔔 **پیام جدید از کاربر!**\n\n"
        f"👤 کاربر: `{user_id}`\n"
        f"💬 پیام:\n{message_text}\n\n"
        f"برای پاسخ از دستور `/sendto {user_id} <پیام>` استفاده کنید."
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 مشاهده تیکت", callback_data=f"admin_ticket_{user_id}"))
    
    for admin_id in config.admin_list:
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as e:
            logger.error(f"خطا در ارسال به ادمین {admin_id}: {e}")

# اضافه کردن متد به کلاس
HelpHandlers.notify_admins_new_message = lambda self, user_id, message_text: notify_admins_new_message_helper(self.bot, self.db, user_id, message_text)
