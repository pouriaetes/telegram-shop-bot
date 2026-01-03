# database.py
# wrapper ساده برای SQLite
# متدهای پایه‌ای که در bot_webhook و ماژول‌ها استفاده می‌شوند
# ✅ تغییر مهم: آماده برای استفاده بدون تنظیمات اضافی

import sqlite3
from typing import Optional, List, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, path: str = 'shop.db'):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self):
        cur = self.conn.cursor()
        # users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            is_admin INTEGER DEFAULT 0,
            balance INTEGER DEFAULT 0,
            created_at INTEGER
        )
        """)
        # products (simple)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT,
            price INTEGER,
            stock_count INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
        """)
        # orders (simple)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            site_name TEXT,
            price INTEGER,
            status TEXT,
            created_at INTEGER
        )
        """)
        self.conn.commit()

    def get_or_create_user(self, telegram_id: int, username: Optional[str], is_admin: bool=False) -> Dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
        created_at = int(time.time())
        cur.execute("INSERT INTO users (telegram_id, username, is_admin, created_at) VALUES (?, ?, ?, ?)",
                    (telegram_id, username, 1 if is_admin else 0, created_at))
        self.conn.commit()
        cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return dict(cur.fetchone())

    def get_active_products(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM products WHERE active = 1")
        rows = cur.fetchall()
        if not rows:
            # نمونه پیش‌فرض (در صورت خالی بودن جدول)
            return [{
                'id': 1,
                'site_name': 'ChatGPT GO',
                'price': 1499000,
                'stock_count': 999
            }]
        return [dict(r) for r in rows]

    def get_user_orders(self, telegram_id: int) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM orders WHERE telegram_id = ? ORDER BY created_at DESC LIMIT 50", (telegram_id,))
        return [dict(r) for r in cur.fetchall()]

    def insert_order(self, telegram_id: int, site_name: str, price: int, status: str = 'pending') -> int:
        cur = self.conn.cursor()
        created_at = int(time.time())
        cur.execute("INSERT INTO orders (telegram_id, site_name, price, status, created_at) VALUES (?, ?, ?, ?, ?)",
                    (telegram_id, site_name, price, status, created_at))
        self.conn.commit()
        return cur.lastrowid

    def get_detailed_statistics(self) -> Dict[str, int]:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) as total_users FROM users")
        total_users = cur.fetchone()['total_users']
        cur.execute("SELECT COUNT(*) as active_products FROM products WHERE active = 1")
        active_products = cur.fetchone()['active_products']
        # بقیه آمارهای ضروری را به شکل ساده اضافه می‌کنیم
        return {
            'real_users': max(total_users - 1, 0),
            'admin_count': 1,
            'total_users': total_users,
            'active_products': active_products,
            'total_products': active_products,
            'available_accounts': 0,
            'sold_accounts': 0,
            'total_sales': 0,
            'total_revenue': 0
        }

    def close(self):
        self.conn.close()
