# Copyright (c) 2026 Vasilyev Fyodor Mikhaylovich (aka Fevazy)
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI

app = FastAPI(
    title="OKNO API v0.0.0 (dev)",
    description="API. I'll describe it later",
    version="0.0.0",
)


@app.get("/echo")
def echo(message: str):
    return {"message": message}
