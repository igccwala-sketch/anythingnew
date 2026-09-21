import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8465860341:AAFYv9bkH-3ST83flC1keAQiJQof3fFDedw")
    OWNER_ID: int = int(os.getenv("OWNER_ID", "8555472509"))
    DATABASE_PATH: str = "gmail_creator_db.sqlite3"

    # Gmail Creation Settings
    MAX_ACCOUNTS_PER_BATCH: int = 10
    PROXY_TIMEOUT: int = 30
    SMS_BYPASS_ENABLED: bool = True

    # Browser Settings
    HEADLESS: bool = True
    USER_AGENT_ROTATION: bool = True

    # Paths
    PROXY_FILE_PATH: str = "proxies.txt"
    COOKIES_PATH: str = "./cookies"

config = Config()
