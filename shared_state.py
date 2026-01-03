# shared_state.py
# ماژول مشترک برای نگهداری stateهای موقت و pending orders
# ✅ تغییر مهم: جلوگیری از circular import بین bot_webhook.py و accountmaker.py

from typing import Dict, Any

# state کاربر: user_id -> state_name
user_states: Dict[int, str] = {}

# داده‌های موقت کاربر (مثلاً order_id): user_id -> dict
user_data: Dict[int, Dict[str, Any]] = {}

# سفارش‌های در انتظار (in-memory). ساختار مشابه آنچه شما مشخص کردی.
pending_orders: Dict[str, Dict[str, Any]] = {}

# شمارنده سفارش (در حافظه)
order_counter = 1
