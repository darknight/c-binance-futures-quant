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

    # Binance API
    binance_api_arr: str = "[]"  # JSON array: [{"apiKey":"...","apiSecret":"...","apiDescribe":"..."}]

    # Web Server
    web_address: str = ""
    cancel_web_address: str = ""

    # Service Identity (replaces Aliyun ECS getServerName)
    server_name: str = ""
    machine_index: int = 0

    # Service Hosts (replaces Aliyun ECS get_aliyun_private_ip_arr_by_name)
    tick_instance_count: int = 1
    vol_rate_host_a: str = ""
    vol_rate_host_b: str = ""
    second_open_hosts: str = "[]"  # JSON array: ["10.0.0.1","10.0.0.2"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
