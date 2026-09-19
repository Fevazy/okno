# Copyright (c) 2026 Vasilyev Fyodor Mikhaylovich (aka Fevazy)
# SPDX-License-Identifier: Apache-2.0
import sqlite3
import datetime

OKNO_TTL_TLE = 7200
OKNO_TTL_KP = 3600
OKNO_TTL_DONKI = 21600
OKNO_TTL_SOCRATES = 43200

OKNO_TIME_COL = {
    "tle": "epoch",
    "kp": "time",
    "cme": "start_time",
    "flr": "begin_time",
    "gst": "start_time",
    "conjunctions": "tca",
}

OKNO_DEFAULT_TTL = {
    "tle": OKNO_TTL_TLE,
    "kp": OKNO_TTL_KP,
    "cme": OKNO_TTL_DONKI,
    "flr": OKNO_TTL_DONKI,
    "gst": OKNO_TTL_DONKI,
    "conjunctions": OKNO_TTL_SOCRATES,
}


def okno_is_covered(
    conn: sqlite3.Connection,
    table: str,
    start: str,
    end: str,
    max_age_seconds: int | None = None,
    cutoff: str | None = None,
) -> bool:
    # таблицы имеют разные колонки времени, поэтому маппинг ниже.
    time_col = OKNO_TIME_COL.get(table)
    if time_col is None:
        return False

    if cutoff is not None:
        # historical: покрыто, если есть хоть одна запись в окне,
        # опубликованная не позже cutoff. Записи "из будущего" игнорируются
        # при чтении (см. okno_select_*), а не считаются причиной для фетча.
        sql = (
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {time_col} >= ? AND {time_col} <= ? AND published_at <= ?"
        )
        cur = conn.execute(sql, (start, end, cutoff))
        count = cur.fetchone()[0]
        if count == 0:
            return False
        return True

    # current: достаточно, чтобы в окне вообще были строки.
    sql = (f"SELECT COUNT(*) FROM {table} WHERE {time_col} >= ? AND "
           f"{time_col} <= ?")
    cur = conn.execute(sql, (start, end))
    count = cur.fetchone()[0]
    if count == 0:
        return False

    if max_age_seconds is not None:
        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = (now - datetime.timedelta(seconds=max_age_seconds)
                     ).isoformat()
        sql = (
            f"SELECT MAX(fetched_at) FROM {table} "
            f"WHERE {time_col} >= ? AND {time_col} <= ?"
        )
        cur = conn.execute(sql, (start, end))
        max_fetched = cur.fetchone()[0]
        # строковое сравнение ISO8601 работает, пока все fetched_at в UTC
        # с одинаковым форматом.
        if max_fetched is None or max_fetched < threshold:
            return False

    return True


def okno_needs_fetch(
    conn: sqlite3.Connection,
    table: str,
    start: str,
    end: str,
    mode: str,
    max_age_seconds: int | None = None,
) -> tuple[bool, str]:
    if table not in OKNO_TIME_COL:
        return True, "UNKNOWN_TABLE"

    if mode == "historical":
        cutoff = start
        covered = okno_is_covered(conn, table, start, end,
                                  max_age_seconds=None,
                                  cutoff=cutoff)
        if not covered:
            return True, "MISSING_HISTORICAL"
        return False, ""

    if mode == "current":
        if max_age_seconds is None:
            max_age_seconds = OKNO_DEFAULT_TTL.get(table)
        if max_age_seconds is None:
            return True, "UNKNOWN_TTL"
        covered = okno_is_covered(conn, table, start, end,
                                  max_age_seconds=max_age_seconds, cutoff=None)
        if not covered:
            time_col = OKNO_TIME_COL[table]
            sql = (f"SELECT COUNT(*) FROM {table} WHERE {time_col} >= ? AND "
                   f"{time_col} <= ?")
            cur = conn.execute(sql, (start, end))
            count = cur.fetchone()[0]
            if count == 0:
                return True, "MISSING_CURRENT"
            return True, "STALE"
        return False, ""

    return True, "INVALID_MODE"


def okno_has_any_data(
    conn: sqlite3.Connection,
    table: str,
    start: str,
    end: str,
    cutoff: str | None,
) -> bool:
    # используется при сбое фетча, чтобы решить: отдать stale-данные или 503.
    time_col = OKNO_TIME_COL.get(table)
    if time_col is None:
        return False
    sql = (f"SELECT COUNT(*) FROM {table} WHERE {time_col} >= ? AND "
           f"{time_col} <= ?")
    params: list = [start, end]
    if cutoff is not None:
        sql += " AND published_at <= ?"
        params.append(cutoff)
    cur = conn.execute(sql, params)
    count = cur.fetchone()[0]
    return count > 0
