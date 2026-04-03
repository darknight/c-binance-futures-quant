import json
import random
import time
from dataclasses import dataclass, field

from infra_client import InfraClient
from settings import settings


@dataclass
class AppState:
    """Centralized mutable state replacing webServer.py global variables."""

    infra_client: InfraClient = field(default=None)

    # Symbol precision info (populated by update_symbol_info)
    price_decimal_obj: dict = field(default_factory=dict)
    amount_decimal_obj: dict = field(default_factory=dict)
    price_tick_obj: dict = field(default_factory=dict)
    price_decimal_amount_obj: dict = field(default_factory=dict)
    amount_decimal_amount_obj: dict = field(default_factory=dict)
    market_max_size_obj: dict = field(default_factory=dict)
    market_min_size_obj: dict = field(default_factory=dict)

    # Order ID generation
    order_id_symbol: str = "wTake"
    order_id_index: int = field(default_factory=lambda: random.randint(1, 100000))
    private_ip: str = ""

    # API key cache {apiKey: apiSecret}
    api_obj: dict = field(default_factory=dict)

    # NEW_API_OBJ: per-symbol API config for watch/position endpoints
    new_api_obj: dict = field(default_factory=dict)

    # Income cache
    income_obj: dict = field(default_factory=lambda: {
        "15m": {"c": 0, "p": 0, "s": 0},
        "30m": {"c": 0, "p": 0, "s": 0},
        "1h": {"c": 0, "p": 0, "s": 0},
        "4h": {"c": 0, "p": 0, "s": 0},
        "oneDay": {"c": 0, "p": 0, "s": 0},
        "today": {"c": 0, "p": 0, "s": 0},
    })
    symbol_income_obj: dict = field(default_factory=dict)
    last_update_income_ts: int = 0
    income_lock: bool = False

    # Account info cache
    account_info_update_ts: int = 0
    bnb_price: float = 0
    position_arr: list = field(default_factory=lambda: [[] for _ in range(10)])
    assets_arr: list = field(default_factory=lambda: [[] for _ in range(10)])

    # Depth cache
    depth_update_ts: int = 0
    last_binance_response_obj: dict = field(default_factory=dict)

    # Open orders cache
    all_open_orders_arr_update_ts: int = 0
    all_open_orders_arr: list = field(default_factory=list)

    # Record cache
    last_record_ts: int = 0
    record_lock: bool = False

    # Day income cache
    update_day_income_ts: int = 0
    get_day_income_ts: int = 0
    get_day_income_today_ts: int = 0
    day_income_data: list = field(default_factory=list)

    # 1-min kline cache
    one_min_update_ts: int = 0
    one_min_kline: list = field(default_factory=list)

    # Trade server status cache
    trade_server_status_data: list = field(default_factory=list)
    update_trade_server_status_data_ts: int = 0
    customize_dangerous_data_arr: list = field(default_factory=list)
    customize_dangerous_data_arr_update_ts: int = 0

    # Trade machine status
    trade_machine_status_data: list = field(default_factory=list)
    update_trade_machine_status_data_ts: int = 0
    average_run_time: int = 0

    # Binance data cache
    eth_1m_kline_arr: list = field(default_factory=list)
    btc_1m_kline_arr: list = field(default_factory=list)
    eth_today_begin_price: dict = field(default_factory=lambda: {"price": 0, "updateTs": 0})
    btc_today_begin_price: dict = field(default_factory=lambda: {"price": 0, "updateTs": 0})
    tick_arr: list = field(default_factory=list)
    update_binance_data_ts: int = 0

    # Turn price cache
    eth_turn_price: float = 0
    btc_turn_price: float = 0
    turn_price_update_ts: int = 0
    eth_turn_ts: int = 0
    btc_turn_ts: int = 0

    # Watch info cache
    watch_info_update_ts: int = 0
    watch_info_obj: dict = field(default_factory=dict)

    # Loss limit time cache
    get_loss_limit_time_data_ts: int = 0
    loss_limit_time_data_arr: list = field(default_factory=list)

    # One day rate cache
    update_one_day_rate_ts: int = 0
    symbol_data_obj: dict = field(default_factory=dict)

    # Cancel orders throttle
    symbol_cancel_orders_ts_obj: dict = field(default_factory=dict)

    # Big loss trades cache
    big_loss_trades_arr: list = field(default_factory=list)
    update_big_loss_trades_data_ts: int = 0

    # Begin trade record throttle
    symbol_last_insert_ts_obj: dict = field(default_factory=dict)

    # Take open state
    take_open_obj: dict = field(default_factory=dict)

    # BNB buy throttle
    buy_bnb_ts: int = 0

    def update_api_obj(self, api_key: str) -> None:
        """Cache API secret for a given key from settings."""
        if api_key in self.api_obj:
            return
        binance_api_arr = json.loads(settings.binance_api_arr)
        for item in binance_api_arr:
            if api_key == item["apiKey"]:
                self.api_obj[item["apiKey"]] = item["apiSecret"]
                break

    def next_order_id(self) -> int:
        """Increment and return the next order ID index."""
        self.order_id_index += 1
        return self.order_id_index
