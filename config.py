from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Optional


class Settings(BaseSettings):
    bot_token: SecretStr
    admin_ids: str
    database_path: str = "shop.db"
    proxy_url: Optional[str] = None
    
    # 👇 فیلدهای پرداخت - اضافه شد 👇
    zibal_merchant: str = ""
    zibal_callback_url: str = ""
    nowpayments_api_key: str = ""
    nowpayments_callback_url: str = ""
    usd_to_toman_rate: int = 65000
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )
    
    @property
    def admin_list(self) -> list[int]:
        return [int(admin_id) for admin_id in self.admin_ids.split(',')]


config = Settings()

