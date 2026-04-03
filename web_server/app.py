from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_server.routers import config, market, orders, trading, income


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


app = create_app()
