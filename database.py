import sqlite3
import logging
from typing import Optional, List
from datetime import datetime
from contextlib import contextmanager
import json

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager برای اتصال به دیتابیس"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self):
        """ایجاد جداول"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 0,
                    is_admin BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    stock INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    requires_form BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول فیلدهای فرم
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_form_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    field_name TEXT NOT NULL,
                    field_label TEXT NOT NULL,
                    field_type TEXT DEFAULT 'text',
                    is_required BOOLEAN DEFAULT 1,
                    field_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    login TEXT NOT NULL,
                    password TEXT NOT NULL,
                    additional_info TEXT,
                    is_sold BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES products(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    account_id INTEGER,
                    form_data TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                    FOREIGN KEY (product_id) REFERENCES products(id),
                    FOREIGN KEY (account_id) REFERENCES accounts(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    order_id INTEGER,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # اضافه کردن ستون‌های جدید اگر وجود ندارند
            try:
                conn.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")
            except:
                pass
            
            try:
                conn.execute("ALTER TABLE products ADD COLUMN requires_form BOOLEAN DEFAULT 0")
            except:
                pass
            
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN form_data TEXT")
            except:
                pass
            
            # ✅ اضافه کردن جداول Account Maker (داخل همین with)
            from accountmaker import AccountMakerDB
            AccountMakerDB.init_tables(conn)
            
            # ✅ جداول Help
            from help import HelpDB
            HelpDB.init_tables(conn)

             # جداول پرداخت زیبال
            from payment_zibal import PaymentZibalDB
            PaymentZibalDB.init_tables(conn)
            
            # جداول پرداخت دیجیتال
            from payment_digital import PaymentDigitalDB
            PaymentDigitalDB.init_tables(conn)
        
        
        
        logger.info("✅ پایگاه داده با موفقیت ایجاد شد")

    def get_or_create_user(self, telegram_id: int, username: Optional[str], is_admin: bool = False):
        """دریافت یا ایجاد کاربر"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            
            conn.execute(
                "INSERT INTO users (telegram_id, username, is_admin) VALUES (?, ?, ?)",
                (telegram_id, username, is_admin)
            )
            
            return {
                'telegram_id': telegram_id,
                'username': username,
                'balance': 0.0,
                'is_admin': is_admin
            }
    
    def get_active_products(self):
        """دریافت محصولات فعال"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT p.*, p.stock as stock_count
                FROM products p
                WHERE p.is_active = 1
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_product_by_id(self, product_id: int):
        """دریافت محصول با ID"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT p.*, p.stock as stock_count
                FROM products p
                WHERE p.id = ?
            """, (product_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ===== Product Form Fields Methods =====
    
    def add_form_field(self, product_id: int, field_name: str, field_label: str, 
                       field_type: str = 'text', is_required: bool = True, field_order: int = 0):
        """افزودن فیلد فرم به محصول"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO product_form_fields 
                (product_id, field_name, field_label, field_type, is_required, field_order)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (product_id, field_name, field_label, field_type, is_required, field_order))
            
            # فعال کردن requires_form برای محصول
            conn.execute(
                "UPDATE products SET requires_form = 1 WHERE id = ?",
                (product_id,)
            )
    
    def get_product_form_fields(self, product_id: int):
        """دریافت فیلدهای فرم محصول"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM product_form_fields
                WHERE product_id = ?
                ORDER BY field_order, id
            """, (product_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_form_field(self, field_id: int):
        """حذف فیلد فرم"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM product_form_fields WHERE id = ?", (field_id,))
    
    def clear_product_form(self, product_id: int):
        """پاک کردن تمام فیلدهای فرم یک محصول"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM product_form_fields WHERE product_id = ?", (product_id,))
            conn.execute("UPDATE products SET requires_form = 0 WHERE id = ?", (product_id,))
    
    # ===== Purchase Methods =====
    
    def purchase_account(self, user_id: int, product_id: int, form_data: dict = None):
        """خرید اکانت با قفل تراکنش"""
        with self.get_connection() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            
            try:
                # بررسی موجودی
                cursor = conn.execute(
                    "SELECT balance FROM users WHERE telegram_id = ?",
                    (user_id,)
                )
                user_row = cursor.fetchone()
                if not user_row:
                    return {"error": "کاربر یافت نشد"}
                
                user_balance = user_row[0]
                
                # دریافت قیمت و موجودی محصول
                cursor = conn.execute(
                    "SELECT price, stock FROM products WHERE id = ? AND is_active = 1",
                    (product_id,)
                )
                product_row = cursor.fetchone()
                if not product_row:
                    return {"error": "محصول یافت نشد"}
                
                price, stock = product_row
                
                if user_balance < price:
                    return {"error": "موجودی ناکافی"}
                
                if stock <= 0:
                    return {"error": "اکانتی موجود نیست"}
                
                # پیدا کردن اکانت آزاد
                cursor = conn.execute("""
                    SELECT id, login, password, additional_info
                    FROM accounts
                    WHERE product_id = ? AND is_sold = 0
                    LIMIT 1
                """, (product_id,))
                
                account_row = cursor.fetchone()
                if not account_row:
                    return {"error": "اکانتی موجود نیست"}
                
                account_id, login, password, additional_info = account_row
                
                # علامت‌گذاری اکانت
                conn.execute(
                    "UPDATE accounts SET is_sold = 1 WHERE id = ?",
                    (account_id,)
                )
                
                # کم کردن موجودی محصول
                conn.execute(
                    "UPDATE products SET stock = stock - 1 WHERE id = ?",
                    (product_id,)
                )
                
                # کاهش موجودی کاربر
                conn.execute(
                    "UPDATE users SET balance = balance - ? WHERE telegram_id = ?",
                    (price, user_id)
                )
                
                # ایجاد سفارش با form_data
                form_data_json = json.dumps(form_data, ensure_ascii=False) if form_data else None
                cursor = conn.execute("""
                    INSERT INTO orders (user_id, product_id, account_id, form_data, status)
                    VALUES (?, ?, ?, ?, 'delivered')
                """, (user_id, product_id, account_id, form_data_json))
                
                order_id = cursor.lastrowid
                
                # ثبت تراکنش
                conn.execute("""
                    INSERT INTO transactions (user_id, order_id, amount, type, description)
                    VALUES (?, ?, ?, 'purchase', 'خرید اکانت')
                """, (user_id, order_id, price))
                
                logger.info(f"✅ خرید موفق - کاربر: {user_id}, محصول: {product_id}")
                
                return {
                    "success": True,
                    "order_id": order_id,
                    "login": login,
                    "password": password,
                    "additional_info": additional_info,
                    "price": price,
                    "form_data": form_data
                }
                
            except Exception as e:
                logger.error(f"❌ خطا در خرید: {e}")
                return {"error": "خطا در پردازش خرید"}
    
    def add_balance(self, user_id: int, amount: float, description: str = "افزایش موجودی"):
        """افزودن موجودی"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                (amount, user_id)
            )
            conn.execute("""
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, 'deposit', ?)
            """, (user_id, amount, description))
    
    def get_user_orders(self, user_id: int):
        """دریافت سفارشات کاربر"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT o.id, o.user_id, o.product_id, o.status, o.created_at,
                       p.site_name, p.price, o.form_data
                FROM orders o
                JOIN products p ON o.product_id = p.id
                WHERE o.user_id = ?
                ORDER BY o.created_at DESC
                LIMIT 20
            """, (user_id,))
            orders = []
            for row in cursor.fetchall():
                order_dict = dict(row)
                if order_dict['form_data']:
                    order_dict['form_data'] = json.loads(order_dict['form_data'])
                orders.append(order_dict)
            return orders
    
    # ===== Admin Methods =====
    
    def add_product(self, site_name: str, description: str, price: float, stock: int = 0):
        """افزودن محصول"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO products (site_name, description, price, stock) VALUES (?, ?, ?, ?)",
                (site_name, description, price, stock)
            )
            return cursor.lastrowid
    
    def add_account(self, product_id: int, login: str, password: str, additional_info: str = ""):
        """افزودن اکانت"""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (product_id, login, password, additional_info) VALUES (?, ?, ?, ?)",
                (product_id, login, password, additional_info)
            )
            # افزایش موجودی محصول
            conn.execute(
                "UPDATE products SET stock = stock + 1 WHERE id = ?",
                (product_id,)
            )
    
    def update_product(self, product_id: int, site_name: str = None, description: str = None, price: float = None):
        """ویرایش محصول"""
        with self.get_connection() as conn:
            updates = []
            params = []
            
            if site_name is not None:
                updates.append("site_name = ?")
                params.append(site_name)
            
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            
            if price is not None:
                updates.append("price = ?")
                params.append(price)
            
            if not updates:
                return False
            
            params.append(product_id)
            query = f"UPDATE products SET {', '.join(updates)} WHERE id = ?"
            conn.execute(query, params)
            return True
    
    def update_product_stock(self, product_id: int, stock: int):
        """تغییر موجودی محصول"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE products SET stock = ? WHERE id = ?",
                (stock, product_id)
            )
            return True
    
    def toggle_product_status(self, product_id: int):
        """تغییر وضعیت محصول"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE products SET is_active = NOT is_active WHERE id = ?",
                (product_id,)
            )
    
    def delete_product(self, product_id: int):
        """حذف محصول"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE product_id = ? AND is_sold = 1",
                (product_id,)
            )
            sold_count = cursor.fetchone()[0]
            
            if sold_count > 0:
                return {"error": "این محصول دارای اکانت‌های فروخته شده است و قابل حذف نیست"}
            
            conn.execute("DELETE FROM accounts WHERE product_id = ? AND is_sold = 0", (product_id,))
            conn.execute("DELETE FROM product_form_fields WHERE product_id = ?", (product_id,))
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            
            return {"success": True}
    
    def get_all_products(self):
        """دریافت همه محصولات"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT p.*, p.stock as stock_count
                FROM products p
                ORDER BY p.id DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_detailed_statistics(self):
        """آمار دقیق"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0")
            real_users = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
            admin_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
            active_products = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM products")
            total_products = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'delivered'")
            total_sales = cursor.fetchone()[0]
            
            cursor = conn.execute("""
                SELECT COALESCE(SUM(p.price), 0)
                FROM orders o
                JOIN products p ON o.product_id = p.id
                WHERE o.status = 'delivered'
            """)
            total_revenue = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM accounts WHERE is_sold = 0")
            available_accounts = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM accounts WHERE is_sold = 1")
            sold_accounts = cursor.fetchone()[0]
            
            return {
                "real_users": real_users,
                "total_users": total_users,
                "admin_count": admin_count,
                "active_products": active_products,
                "total_products": total_products,
                "total_sales": total_sales,
                "total_revenue": total_revenue,
                "available_accounts": available_accounts,
                "sold_accounts": sold_accounts
            }
