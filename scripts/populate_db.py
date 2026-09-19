"""Одноразовый ingest архивных данных за 2024-05-01 .. 2024-06-30.

Запуск: python scripts/ingest_historical.py
"""

import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
load_dotenv()

# пути: добавить src в sys.path, чтобы импорты работали.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

import okno_db
from fetchers import donki as okno_donki
from fetchers import tle as okno_tle


OKNO_DB_PATH = os.path.join(_ROOT, "okno.db")

START_DATE = "2024-05-01"
END_DATE = "2024-06-30"

# GFZ Potsdam отдаёт Kp-индекс в JSON с 1932 года.
# API: https://kp.gfz-potsdam.de/app/json/
GFZ_KP_URL = "https://kp.gfz-potsdam.de/app/json/"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def okno_fetch_kp_archive(start_date: str, end_date: str) -> list[dict]:
    # GFZ принимает ISO-строки; end включает весь день.
    params = {
        "start": f"{start_date}T00:00:00Z",
        "end": f"{end_date}T23:59:59Z",
        "index": "Kp",
    }
    r = requests.get(GFZ_KP_URL, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"gfz kp: HTTP {r.status_code}")

    data = r.json()
    # ожидаемый формат: {"datetime": [...], "Kp": [...], ...}
    times = data.get("datetime") or data.get("time_tag") or []
    kps = data.get("Kp") or data.get("kp") or []

    if not times or not kps or len(times) != len(kps):
        raise RuntimeError(f"gfz kp: unexpected payload keys={list(data.keys())}")

    fetched_at = _now()
    out: list[dict] = []
    for t, kp in zip(times, kps):
        if kp is None:
            continue
        out.append({
            "time": t,
            "kp": float(kp),
            "published_at": t,
            "fetched_at": fetched_at,
            "source": "gfz_potsdam",
        })
    return out


def okno_fetch_tle_current() -> list[dict]:
    # ВАЖНО: исторических TLE у Celestrak в открытом API нет.
    # Для демонстрации historical-режима берём текущий TLE.
    # В отчёте это явно указано как ограничение.
    return okno_tle.okno_fetch_tle()


def main() -> None:
    print(f"[ingest] opening db: {OKNO_DB_PATH}")
    conn = okno_db.okno_open(OKNO_DB_PATH)
    okno_db.okno_init_schema(conn)

    # 1. Kp из архива GFZ
    print(f"[ingest] fetching Kp archive {START_DATE}..{END_DATE}")
    try:
        kp_rows = okno_fetch_kp_archive(START_DATE, END_DATE)
        n = okno_db.okno_upsert_kp(conn, kp_rows)
        print(f"[ingest]   kp: {len(kp_rows)} rows, upserted {n}")
    except Exception as e:
        print(f"[ingest]   kp FAILED: {type(e).__name__}: {e}")

    # 2. DONKI: CME, FLR, GST
    for name, fetcher, upsert in (
        ("cme", okno_donki.okno_fetch_cme, okno_db.okno_upsert_cme),
        ("flr", okno_donki.okno_fetch_flr, okno_db.okno_upsert_flr),
        ("gst", okno_donki.okno_fetch_gst, okno_db.okno_upsert_gst),
    ):
        print(f"[ingest] fetching DONKI {name} {START_DATE}..{END_DATE}")
        try:
            rows = fetcher(START_DATE, END_DATE)
            n = upsert(conn, rows)
            print(f"[ingest]   {name}: {len(rows)} rows, upserted {n}")
        except Exception as e:
            print(f"[ingest]   {name} FAILED: {type(e).__name__}: {e}")

    # 3. TLE (текущий, как прокси для historical)
    print("[ingest] fetching current TLE (proxy for historical)")
    try:
        tle_rows = okno_fetch_tle_current()
        n = okno_db.okno_upsert_tle(conn, tle_rows)
        print(f"[ingest]   tle: {len(tle_rows)} rows, upserted {n}")
    except Exception as e:
        print(f"[ingest]   tle FAILED: {type(e).__name__}: {e}")

    # 4. SOCRATES для 2024 недоступен через открытый API — пропускаем.
    print("[ingest] conjunctions: skipped (no public archive for 2024)")

    # итоговые счётчики
    print("[ingest] final row counts:")
    for table in ("kp", "cme", "flr", "gst", "tle", "conjunctions"):
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"[ingest]   {table}: {cur.fetchone()[0]}")

    okno_db.okno_close(conn)
    print("[ingest] done")


if __name__ == "__main__":
    main()
