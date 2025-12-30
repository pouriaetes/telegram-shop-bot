from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_site_name = State()
    waiting_for_description = State()
    waiting_for_price = State()
    
    waiting_for_product_id_for_account = State()
    waiting_for_login = State()
    waiting_for_password = State()
    waiting_for_additional_info = State()
    
    waiting_for_user_id_balance = State()
    waiting_for_balance_amount = State()
