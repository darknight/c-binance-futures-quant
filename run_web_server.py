#!/usr/bin/env python3
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web_server.app:app", host="0.0.0.0", port=8888, workers=1)
