# Copyright (c) 2026 Vasilyev Fyodor Mikhaylovich (aka Fevazy)
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
import sqlite3
import datetime
import okno_db
import okno_pipeline

OKNO_DB_PATH = "okno.db"

app = FastAPI(title="OKNO API", version="0.1.0")


@app.on_event("startup")
def okno_startup() -> None:
    conn = okno_db.okno_open(OKNO_DB_PATH)
    okno_db.okno_init_schema(conn)
    okno_db.okno_close(conn)


def okno_get_db():
    conn = okno_db.okno_open(OKNO_DB_PATH)
    try:
        yield conn
    finally:
        okno_db.okno_close(conn)


class OknoEvaluateRequest(BaseModel):
    start: str
    end: str
    step_minutes: int = 10
    mode: str = "current"


class OknoWindowSpec(BaseModel):
    id: str
    start: str
    end: str


class OknoCompareRequest(BaseModel):
    windows: List[OknoWindowSpec]
    mode: str = "current"


def okno_validate_request(start: str, end: str, mode: str) -> None:
    try:
        dt_start = datetime.datetime.fromisoformat(start)
        dt_end = datetime.datetime.fromisoformat(end)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO datetime: {exc}") from exc

    if dt_start >= dt_end:
        raise ValueError("start must be strictly before end")

    hours = (dt_end - dt_start).total_seconds() / 3600.0
    if not (1 <= hours <= 8):
        raise ValueError("Window duration must be between 1 and 8 hours")

    if mode not in {"current", "historical"}:
        raise ValueError("mode must be 'current' or 'historical'")

    if mode == "historical":
        hist_min = datetime.datetime.fromisoformat("2024-05-01T00:00:00+00:00")
        hist_max = datetime.datetime.fromisoformat("2024-07-01T00:00:00+00:00")
        if not (hist_min <= dt_start <= hist_max):
            raise ValueError(
                "Historical start must be within 2024-05-01T00:00:00+00:00 "
                "and 2024-07-01T00:00:00+00:00"
            )


@app.exception_handler(RequestValidationError)
async def okno_validation_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "reason_code": "VALIDATION_ERROR",
            "message": "Invalid request payload",
            "details": exc.errors(),
        },
    )


@app.post("/evaluate")
def okno_evaluate(
    req: OknoEvaluateRequest,
    conn: sqlite3.Connection = Depends(okno_get_db),
):
    try:
        okno_validate_request(req.start, req.end, req.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "reason_code": "VALIDATION_ERROR",
                "message": str(exc),
            },
        )

    result = okno_pipeline.okno_evaluate_window(
        conn, req.start, req.end, req.step_minutes, req.mode
    )
    return result


@app.post("/compare")
def okno_compare(
    req: OknoCompareRequest,
    conn: sqlite3.Connection = Depends(okno_get_db),
):
    for w in req.windows:
        try:
            okno_validate_request(w.start, w.end, req.mode)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "error",
                    "reason_code": "VALIDATION_ERROR",
                    "message": str(exc),
                },
            )

    result = okno_pipeline.okno_compare_windows(
        conn, [w.dict() for w in req.windows], req.mode
    )
    return result


@app.get("/factors")
def okno_factors():
    return [
        {"name": "kp",
         "description": "Планетарный Kp-индекс геомагнитной активности"},
        {"name": "cme",
         "description": "Корональные выбросы массы"},
        {"name": "flr",
         "description": "Солнечные вспышки (рентгеновский поток)"},
        {"name": "gst",
         "description": "Геомагнитные бури"},
        {"name": "conjunctions",
         "description": "Сближения с космическим мусором"},
    ]


@app.get("/health")
def okno_health():
    return {"status": "ok"}
