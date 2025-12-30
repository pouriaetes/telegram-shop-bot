from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.user_kb import (
    main_menu_keyboard,
    products_keyboard,
    product_detail_keyboard,
    back_to_main_keyboard
)
from database import Database

user_router = Router()

@user_router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    """دستور /start"""
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )
    
    await message.answer(
        f"🌟 سلام {message.from_user.first_name} عزیز!\n\n"
        f"به فروشگاه اکانت خوش آمدید.\n"
        f"برای شروع، یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_keyboard()
    )

@user_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """بازگشت به منوی اصلی"""
    await callback.message.edit_text(
        "🏠 منوی اصلی:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@user_router.callback_query(F.data == "products_list")
async def show_products(callback: CallbackQuery, db: Database):
    """نمایش لیست محصولات"""
    products = await db.get_active_products()
    
    if not products:
        await callback.message.edit_text(
            "❌ در حال حاضر محصولی موجود نیست.",
            reply_markup=back_to_main_keyboard()
        )
    else:
        await callback.message.edit_text(
            "🛒 لیست محصولات موجود:\n\n"
            "محصول مورد نظر خود را انتخاب کنید:",
            reply_markup=products_keyboard(products)
        )
    
    await callback.answer()

@user_router.callback_query(F.data.startswith("product_"))
async def show_product_detail(callback: CallbackQuery, db: Database):
    """نمایش جزئیات محصول"""
    product_id = int(callback.data.split("_")[1])
    product = await db.get_product_by_id(product_id)
    
    if not product:
        await callback.answer("❌ محصول یافت نشد!", show_alert=True)
        return
    
    stock_status = "✅ موجود" if product.stock_count > 0 else "❌ ناموجود"
    
    text = (
        f"📦 **{product.site_name}**\n\n"
        f"📝 توضیحات:\n{product.description}\n\n"
        f"💰 قیمت: {product.price:,.0f} تومان\n"
        f"📊 موجودی: {product.stock_count} عدد\n"
        f"🔔 وضعیت: {stock_status}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=product_detail_keyboard(product_id, product.stock_count > 0),
        parse_mode="Markdown"
    )
    await callback.answer()

@user_router.callback_query(F.data.startswith("buy_"))
async def process_purchase(callback: CallbackQuery, db: Database):
    """پردازش خرید"""
    product_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    # خرید اکانت
    result = await db.purchase_account(user_id, product_id)
    
    if result and result.get("success"):
        # ارسال اطلاعات اکانت
        account_info = (
            f"✅ **خرید موفق!**\n\n"
            f"🔑 **اطلاعات اکانت شما:**\n\n"
            f"👤 نام کاربری: `{result['login']}`\n"
            f"🔐 رمز عبور: `{result['password']}`\n"
        )
        
        if result.get('additional_info'):
            account_info += f"\n📋 اطلاعات تکمیلی:\n{result['additional_info']}\n"
        
        account_info += (
            f"\n💰 مبلغ پرداختی: {result['price']:,.0f} تومان\n"
            f"🆔 شماره سفارش: #{result['order_id']}\n\n"
            f"⚠️ لطفاً اطلاعات خود را در جای امن ذخیره کنید."
        )
        
        await callback.message.answer(
            account_info,
            parse_mode="Markdown",
            reply_markup=back_to_main_keyboard()
        )
        
        await callback.message.delete()
        await callback.answer("✅ خرید با موفقیت انجام شد!", show_alert=True)
        
    elif result and "error" in result:
        await callback.answer(f"❌ {result['error']}", show_alert=True)
    else:
        await callback.answer("❌ خطا در پردازش خرید", show_alert=True)

@user_router.callback_query(F.data == "wallet")
async def show_wallet(callback: CallbackQuery, db: Database):
    """نمایش کیف پول"""
    user = await db.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username
    )
    
    text = (
        f"💳 **کیف پول شما**\n\n"
        f"💰 موجودی: {user.balance:,.0f} تومان\n\n"
        f"برای افزایش موجودی با پشتیبانی تماس بگیرید."
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=back_to_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@user_router.callback_query(F.data == "my_orders")
async def show_orders(callback: CallbackQuery, db: Database):
    """نمایش سفارشات کاربر"""
    orders = await db.get_user_orders(callback.from_user.id)
    
    if not orders:
        await callback.message.edit_text(
            "📦 شما هنوز سفارشی ثبت نکرده‌اید.",
            reply_markup=back_to_main_keyboard()
        )
    else:
        text = "📦 **سفارش‌های شما:**\n\n"
        
        for order in orders[:10]:  # نمایش 10 سفارش اخیر
            status_emoji = {
                "delivered": "✅",
                "pending": "⏳",
                "cancelled": "❌"
            }.get(order.status, "❓")
            
            text += (
                f"{status_emoji} سفارش #{order.id}\n"
                f"📦 محصول: {order.product_name}\n"
                f"💰 مبلغ: {order.price:,.0f} تومان\n"
                f"📅 تاریخ: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            )
        
        await callback.message.edit_text(
            text,
            reply_markup=back_to_main_keyboard(),
            parse_mode="Markdown"
        )
    
    await callback.answer()

@user_router.callback_query(F.data == "support")
async def show_support(callback: CallbackQuery):
    """نمایش اطلاعات پشتیبانی"""
    text = (
        "📞 **پشتیبانی**\n\n"
        "برای تماس با پشتیبانی از راه‌های زیر استفاده کنید:\n\n"
        "📩 پشتیبانی تلگرام: @YourSupportBot\n"
        "📧 ایمیل: support@example.com\n\n"
        "⏰ پاسخگویی: همه روزه ۹ صبح تا ۱۲ شب"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=back_to_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()
