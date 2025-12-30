from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
from models import Product

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """منوی اصلی کاربر"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 لیست محصولات", callback_data="products_list")],
        [InlineKeyboardButton(text="💳 کیف پول", callback_data="wallet")],
        [InlineKeyboardButton(text="📦 سفارش‌های من", callback_data="my_orders")],
        [InlineKeyboardButton(text="📞 پشتیبانی", callback_data="support")]
    ])
    return keyboard

def products_keyboard(products: List[Product]) -> InlineKeyboardMarkup:
    """لیست محصولات"""
    buttons = []
    
    for product in products:
        stock_emoji = "✅" if product.stock_count > 0 else "❌"
        button_text = f"{stock_emoji} {product.site_name} ({product.stock_count} عدد)"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"product_{product.id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def product_detail_keyboard(product_id: int, has_stock: bool) -> InlineKeyboardMarkup:
    """جزئیات محصول"""
    buttons = []
    
    if has_stock:
        buttons.append([InlineKeyboardButton(
            text="💳 خرید",
            callback_data=f"buy_{product_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="products_list")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """دکمه بازگشت به منوی اصلی"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="back_to_main")]
    ])
