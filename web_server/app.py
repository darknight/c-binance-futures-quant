import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infra_client import InfraClient
from web_server.state import AppState
from web_server.binance_helpers import update_symbol_info
from web_server.routers import config, market, orders, trading, income, records, status, account


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize state
    state = AppState()
    state.infra_client = InfraClient(larkMsgSymbol="webServer", connectMysqlPool=True)
    state.private_ip = state.infra_client.get_private_ip()

    # Load symbol info
    update_symbol_info(state)
    while "BTCUSDT" not in state.price_decimal_obj:
        state.infra_client.send_notify("mainConsole updateSymbolInfo")
        update_symbol_info(state)
        time.sleep(1)

    app.state.app_state = state
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(config.router)
    app.include_router(market.router)
    app.include_router(orders.router)
    app.include_router(trading.router)
    app.include_router(income.router)
    app.include_router(records.router)
    app.include_router(status.router)
    app.include_router(account.router)

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


app = create_app()
