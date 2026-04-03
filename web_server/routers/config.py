import json

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from settings import settings
from app.models.trade_symbol import TradeSymbol

router = APIRouter()

USER_CONFIG_PATH = "user_config.json"


def load_user_config():
    try:
        with open(USER_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"hot_key_config_obj": {}, "state_config_obj": {}}


def save_user_config(config):
    with open(USER_CONFIG_PATH, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


@router.post("/get_config")
def get_config():
    config = load_user_config()
    binance_api_arr = json.loads(settings.binance_api_arr)
    for item in binance_api_arr:
        item["apiSecret"] = ""
    return {
        "s": "ok",
        "binanceApiArr": binance_api_arr,
        "hotKeyConfigObj": config.get("hot_key_config_obj", {}),
        "stateConfigObj": config.get("state_config_obj", {}),
    }


@router.post("/get_symbol_index")
def get_symbol_index(request: Request):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        rows = session.exec(
            select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
        ).all()

    trade_symbol_arr = []
    for i in range(len(rows)):
        link_data = rows[i].link_symbol_arr if isinstance(rows[i].link_symbol_arr, (list, dict)) else json.loads(rows[i].link_symbol_arr or "[]")
        trade_symbol_arr.append({
            "symbol": rows[i].symbol,
            "coin": rows[i].coin,
            "symbolIndex": rows[i].index,
            "quote": rows[i].quote,
            "linkSymbolArr": link_data,
            "defaultShow": rows[i].default_show,
            "weight": 0,
        })

    return {"s": "ok", "d": trade_symbol_arr}


@router.post("/modify_hot_key")
def modify_hot_key(newHotKeyConfigObj: str = Form()):
    new_config = json.loads(newHotKeyConfigObj)
    config = load_user_config()
    config["hot_key_config_obj"] = new_config
    save_user_config(config)
    return {"s": "ok", "newHotKeyConfigObj": new_config}


@router.post("/get_state_config")
def get_state_config():
    config = load_user_config()
    state_config_obj = config.get("state_config_obj", {})
    return {"s": "ok", "stateConfigObj": state_config_obj}


@router.post("/modify_state_config")
def modify_state_config(stateConfigObj: str = Form()):
    state_config = json.loads(stateConfigObj)
    config = load_user_config()
    config["state_config_obj"] = state_config
    save_user_config(config)
    return {"s": "ok", "stateConfigObj": state_config}
