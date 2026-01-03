# config.py
# مدیریت تنظیمات از .env یا متغیرهای محیطی
# استفاده: from config import config
# ✅ تغییر مهم: یکپارچه‌سازی admin_list و مسیر دیتابیس

from pydantic import BaseSettings, SecretStr, Field
from typing import List, Optional

class Settings(BaseSettings):
    bot_token: SecretStr = Field(..., env='BOT_TOKEN')
    admin_ids: str = Field(..., env='ADMIN_IDS')  # comma separated
    database_path: str = Field('shop.db', env='DATABASE_PATH')
    proxy_url: Optional[str] = Field(None, env='PROXY_URL')
    zibal_merchant: Optional[str] = Field(None, env='ZIBAL_MERCHANT')
    zibal_callback_url: Optional[str] = Field(None, env='ZIBAL_CALLBACK_URL')
    nowpayments_api_key: Optional[str] = Field(None, env='NOWPAYMENTS_API_KEY')
    nowpayments_callback_url: Optional[str] = Field(None, env='NOWPAYMENTS_CALLBACK_URL')
    usd_to_toman_rate: int = Field(65000, env='USD_TO_TOMAN_RATE')

    # deployment domains
    railway_public_domain: Optional[str] = Field(None, env='RAILWAY_PUBLIC_DOMAIN')
    render_external_url: Optional[str] = Field(None, env='RENDER_EXTERNAL_URL')

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

    @property
    def admin_list(self) -> List[int]:
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(',') if x.strip()]

config = Settings()
