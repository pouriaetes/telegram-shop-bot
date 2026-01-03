from pydantic import SecretStr
from pydantic_settings import BaseSettings
import os

class Config(BaseSettings):
    bot_token: SecretStr
    database_path: str = "shop.db"
    proxy_url: str = ""
    admin_list: list[int] = []
    
    class Config:
        env_file = ".env"
        
    @classmethod
    def from_env(cls):
        return cls(
            bot_token=SecretStr(os.getenv("BOT_TOKEN", "")),
            database_path=os.getenv("DATABASE_PATH", "bot_database.db"),
            proxy_url=os.getenv("PROXY_URL", ""),
            admin_list=[int(x) for x in os.getenv("ADMIN_LIST", "").split(",") if x]
        )

config = Config.from_env()

