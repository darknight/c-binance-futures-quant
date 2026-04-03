from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://localhost:5432/quant"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # WebSocket Server
    ws_address_a: str = ""
    ws_address_b: str = ""

    # Aliyun (保留，后续迁移时再移除)
    aliyun_api_key: str = ""
    aliyun_api_secret: str = ""
    aliyun_point: str = "ap-northeast-1"

    # Binance API
    binance_api_arr: str = "[]"  # JSON array: [{"apiKey":"...","apiSecret":"...","apiDescribe":"..."}]

    # Web Server
    web_address: str = ""
    cancel_web_address: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
