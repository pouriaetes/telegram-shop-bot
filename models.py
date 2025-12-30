from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class User:
    telegram_id: int
    username: Optional[str]
    balance: float
    is_admin: bool
    created_at: datetime

@dataclass
class Product:
    id: int
    site_name: str
    description: str
    price: float
    is_active: bool
    stock_count: int

@dataclass
class Account:
    id: int
    product_id: int
    login: str
    password: str
    is_sold: bool
    additional_info: Optional[str]

@dataclass
class Order:
    id: int
    user_id: int
    product_id: int
    account_id: int
    status: str  # pending, paid, delivered, cancelled
    created_at: datetime
    product_name: str
    price: float
