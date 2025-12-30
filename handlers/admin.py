from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.admin_kb import (
    admin_menu_keyboard,
    admin_products_keyboard,
    admin_product_actions_keyboard,
    cancel_keyboard
)
from utils.states import AdminStates
from database import Database
from config import config

admin_router = Router()

def is_admin(user_id: int) -> bool:
    """بررسی ادمین بودن کاربر"""
    return user_id in config.admin_list

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """دستور /admin"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ شما دسترسی ادمین ندارید!")
        return
    
    await message.answer(
        "🔧 **پنل مدیریت**\n\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: CallbackQuery, state: FSMContext):
    """نمایش منوی ادمین"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    await state.clear()
    await callback.message.edit_text(
        "🔧 **پنل مدیریت**",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ===== افزودن محصول =====

@admin_router.callback_query(F.data == "admin_add_product")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    """شروع افزودن محصول"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ **افزودن محصول جدید**\n\n"
        "نام سایت را وارد کنید:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_site_name)
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_site_name)
async def process_site_name(message: Message, state: FSMContext):
    """دریافت نام سایت"""
    await state.update_data(site_name=message.text)
    await message.answer(
        "📝 توضیحات محصول را وارد کنید:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_description)

@admin_router.message(AdminStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    """دریافت توضیحات"""
    await state.update_data(description=message.text)
    await message.answer(
        "💰 قیمت محصول را به تومان وارد کنید:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_price)

@admin_router.message(AdminStates.waiting_for_price)
async def process_price(message: Message, state: FSMContext, db: Database):
    """دریافت قیمت و ثبت محصول"""
    try:
        price = float(message.text.replace(',', ''))
        
        if price <= 0:
            await message.answer("❌ قیمت باید بیشتر از صفر باشد!")
            return
        
        data = await state.get_data()
        product_id = await db.add_product(
            site_name=data['site_name'],
            description=data['description'],
            price=price
        )
        
        await message.answer(
            f"✅ محصول با موفقیت اضافه شد!\n\n"
            f"🆔 شناسه محصول: {product_id}\n"
            f"📦 نام: {data['site_name']}\n"
            f"💰 قیمت: {price:,.0f} تومان",
            reply_markup=admin_menu_keyboard()
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")

# ===== افزودن اکانت =====

@admin_router.callback_query(F.data == "admin_add_account")
async def start_add_account(callback: CallbackQuery, state: FSMContext, db: Database):
    """شروع افزودن اکانت"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    products = await db.get_all_products()
    
    if not products:
        await callback.message.edit_text(
            "❌ هیچ محصولی یافت نشد. ابتدا محصول اضافه کنید.",
            reply_markup=admin_menu_keyboard()
        )
        await callback.answer()
        return
    
    products_text = "\n".join([
        f"🆔 {p.id} - {p.site_name} (موجودی: {p.stock_count})"
        for p in products
    ])
    
    await callback.message.edit_text(
        f"📦 **افزودن اکانت**\n\n"
        f"محصولات موجود:\n{products_text}\n\n"
        f"شناسه محصول را وارد کنید:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_product_id_for_account)
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_product_id_for_account)
async def process_product_id_for_account(message: Message, state: FSMContext, db: Database):
    """دریافت شناسه محصول"""
    try:
        product_id = int(message.text)
        product = await db.get_product_by_id(product_id)
        
        if not product:
            await message.answer("❌ محصول با این شناسه یافت نشد!")
            return
        
        await state.update_data(product_id=product_id)
        await message.answer(
            f"✅ محصول: {product.site_name}\n\n"
            f"👤 نام کاربری (Login) را وارد کنید:",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_for_login)
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")

@admin_router.message(AdminStates.waiting_for_login)
async def process_login(message: Message, state: FSMContext):
    """دریافت نام کاربری"""
    await state.update_data(login=message.text)
    await message.answer(
        "🔐 رمز عبور (Password) را وارد کنید:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_password)

@admin_router.message(AdminStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    """دریافت رمز عبور"""
    await state.update_data(password=message.text)
    await message.answer(
        "📋 اطلاعات تکمیلی (اختیاری) را وارد کنید یا /skip بزنید:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_additional_info)

@admin_router.message(AdminStates.waiting_for_additional_info)
async def process_additional_info(message: Message, state: FSMContext, db: Database):
    """دریافت اطلاعات تکمیلی و ثبت اکانت"""
    additional_info = "" if message.text == "/skip" else message.text
    
    data = await state.get_data()
    await db.add_account(
        product_id=data['product_id'],
        login=data['login'],
        password=data['password'],
        additional_info=additional_info
    )
    
    await message.answer(
        "✅ اکانت با موفقیت اضافه شد!",
        reply_markup=admin_menu_keyboard()
    )
    await state.clear()

# ===== مدیریت محصولات =====

@admin_router.callback_query(F.data == "admin_manage_products")
async def manage_products(callback: CallbackQuery, db: Database):
    """مدیریت محصولات"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    products = await db.get_all_products()
    
    if not products:
        await callback.message.edit_text(
            "❌ هیچ محصولی یافت نشد.",
            reply_markup=admin_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            "📊 **مدیریت محصولات**\n\n"
            "محصول مورد نظر را انتخاب کنید:",
            reply_markup=admin_products_keyboard(products),
            parse_mode="Markdown"
        )
    
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_product_"))
async def show_product_actions(callback: CallbackQuery, db: Database):
    """نمایش عملیات محصول"""
    product_id = int(callback.data.split("_")[2])
    product = await db.get_product_by_id(product_id)
    
    if not product:
        await callback.answer("❌ محصول یافت نشد!", show_alert=True)
        return
    
    status = "✅ فعال" if product.is_active else "❌ غیرفعال"
    
    text = (
        f"📦 **{product.site_name}**\n\n"
        f"📝 توضیحات: {product.description}\n"
        f"💰 قیمت: {product.price:,.0f} تومان\n"
        f"📊 موجودی: {product.stock_count} عدد\n"
        f"🔔 وضعیت: {status}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_product_actions_keyboard(product_id, product.is_active),
        parse_mode="Markdown"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_toggle_"))
async def toggle_product(callback: CallbackQuery, db: Database):
    """تغییر وضعیت محصول"""
    product_id = int(callback.data.split("_")[2])
    
    await db.toggle_product_status(product_id)
    await callback.answer("✅ وضعیت محصول تغییر کرد", show_alert=True)
    
    # نمایش مجدد
    await show_product_actions(callback, db)

# ===== افزایش موجودی =====

@admin_router.callback_query(F.data == "admin_add_balance")
async def start_add_balance(callback: CallbackQuery, state: FSMContext):
    """شروع افزایش موجودی"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💰 **افزایش موجودی کاربر**\n\n"
        "ID تلگرام کاربر را وارد کنید:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_user_id_balance)
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_user_id_balance)
async def process_user_id_balance(message: Message, state: FSMContext):
    """دریافت ID کاربر"""
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await message.answer(
            "💵 مبلغ را به تومان وارد کنید:",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_for_balance_amount)
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")

@admin_router.message(AdminStates.waiting_for_balance_amount)
async def process_balance_amount(message: Message, state: FSMContext, db: Database):
    """دریافت مبلغ و افزایش موجودی"""
    try:
        amount = float(message.text.replace(',', ''))
        
        if amount <= 0:
            await message.answer("❌ مبلغ باید بیشتر از صفر باشد!")
            return
        
        data = await state.get_data()
        await db.add_balance(
            user_id=data['user_id'],
            amount=amount,
            description=f"افزایش موجودی توسط ادمین {message.from_user.id}"
        )
        
        await message.answer(
            f"✅ موجودی کاربر {data['user_id']} به مبلغ {amount:,.0f} تومان افزایش یافت!",
            reply_markup=admin_menu_keyboard()
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")

# ===== آمار فروش =====

@admin_router.callback_query(F.data == "admin_statistics")
async def show_statistics(callback: CallbackQuery, db: Database):
    """نمایش آمار فروش"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ دسترسی غیرمجاز!", show_alert=True)
        return
    
    stats = await db.get_sales_statistics()
    
    text = (
        f"📈 **آمار فروش**\n\n"
        f"👥 تعداد کاربران: {stats['total_users']}\n"
        f"📦 محصولات فعال: {stats['active_products']}\n"
        f"💰 تعداد فروش: {stats['total_sales']}\n"
        f"💵 مجموع درآمد: {stats['total_revenue']:,.0f} تومان"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()
