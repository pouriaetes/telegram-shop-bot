from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
from models import Product

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """منوی ادمین"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن محصول", callback_data="admin_add_product")],
        [InlineKeyboardButton(text="📦 افزودن اکانت", callback_data="admin_add_account")],
        [InlineKeyboardButton(text="📊 مدیریت محصولات", callback_data="admin_manage_products")],
        [InlineKeyboardButton(text="💰 افزایش موجودی کاربر", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="📈 آمار فروش", callback_data="admin_statistics")],
        [InlineKeyboardButton(text="👤 منوی کاربر", callback_data="back_to_main")]
    ])
    return keyboard

def admin_products_keyboard(products: List[Product]) -> InlineKeyboardMarkup:
    """لیست محصولات برای ادمین"""
    buttons = []
    
    for product in products:
        status_emoji = "✅" if product.is_active else "❌"
        button_text = f"{status_emoji} {product.site_name} (موجودی: {product.stock_count})"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"admin_product_{product.id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_product_actions_keyboard(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """عملیات محصول"""
    toggle_text = "❌ غیرفعال کردن" if is_active else "✅ فعال کردن"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=toggle_text,
            callback_data=f"admin_toggle_{product_id}"
        )],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_manage_products")]
    ])
    return keyboard

def cancel_keyboard() -> InlineKeyboardMarkup:
    """دکمه لغو"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data="admin_menu")]
    ])
