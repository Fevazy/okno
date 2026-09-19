# Copyright (c) 2026 Vasilyev Fyodor Mikhaylovich (aka Fevazy)
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

import okno_db
import okno_coverage
import okno_trajectory
import okno_scoring

from fetchers import tle as okno_tle
from fetchers import kp as okno_kp
from fetchers import donki as okno_donki
from fetchers import socrates as okno_socrates


TTL_FOR = {
    "kp": 3600,
    "cme": 21600,
    "flr": 21600,
    "gst": 21600,
    "conjunctions": 43200,
    "tle": 7200,
}

SOURCES = ["kp", "cme", "flr", "gst", "conjunctions", "tle"]


def _lookback(date_str: str, days: int) -> str:
    d = datetime.fromisoformat(date_str)
    d = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=days)).strftime("%Y-%m-%d")


def _call_fetcher(table: str, start: str, end: str):
    # фетчеры имеют разные сигнатуры, поэтому диспетчер, а не единый вызов.
    start_date = start[:10]
    end_date = end[:10]
    if table == "kp":
        return okno_kp.okno_fetch_kp()
    if table == "tle":
        return okno_tle.okno_fetch_tle()
    if table == "cme":
        # для current: смотрим на неделю назад, чтобы поймать активные события.
        return okno_donki.okno_fetch_cme(_lookback(start_date, 7), end_date)
    if table == "flr":
        return okno_donki.okno_fetch_flr(_lookback(start_date, 7), end_date)
    if table == "gst":
        return okno_donki.okno_fetch_gst(_lookback(start_date, 7), end_date)
    if table == "conjunctions":
        return okno_socrates.okno_fetch_conjunctions()
    raise ValueError(f"unknown table: {table}")


def _upsert(table: str, conn: Any, rows: list) -> int:
    if table == "kp":
        return okno_db.okno_upsert_kp(conn, rows)
    if table == "tle":
        return okno_db.okno_upsert_tle(conn, rows)
    if table == "cme":
        return okno_db.okno_upsert_cme(conn, rows)
    if table == "flr":
        return okno_db.okno_upsert_flr(conn, rows)
    if table == "gst":
        return okno_db.okno_upsert_gst(conn, rows)
    if table == "conjunctions":
        return okno_db.okno_upsert_conjunctions(conn, rows)
    raise ValueError(f"unknown table: {table}")


def _select(table: str, conn: Any, start: str, end: str, cutoff: Optional[str]):
    if table == "kp":
        return okno_db.okno_select_kp(conn, start, end, cutoff=cutoff)
    if table == "cme":
        return okno_db.okno_select_cme(conn, start, end, cutoff=cutoff)
    if table == "flr":
        return okno_db.okno_select_flr(conn, start, end, cutoff=cutoff)
    if table == "gst":
        return okno_db.okno_select_gst(conn, start, end, cutoff=cutoff)
    if table == "conjunctions":
        return okno_db.okno_select_conjunctions(conn, start, end, cutoff=cutoff)
    if table == "tle":
        return okno_db.okno_select_latest_tle(conn)
    raise ValueError(f"unknown table: {table}")


def okno_ensure_data(conn: Any, table: str, start: str, end: str, mode: str) -> Dict[str, str]:
    if mode == "historical":
        # для historical сеть не трогаем вообще: архив уже в БД.
        cutoff = start
        if okno_coverage.okno_is_covered(conn, table, start, end, cutoff=cutoff):
            return {"status": "fresh", "reason": ""}
        if okno_coverage.okno_has_any_data(conn, table, start, end, cutoff):
            return {"status": "stale", "reason": "PARTIAL_HISTORICAL"}
        return {"status": "no_data", "reason": "MISSING_HISTORICAL"}

    need, reason = okno_coverage.okno_needs_fetch(
        conn, table, start, end, mode, max_age_seconds=TTL_FOR[table]
    )
    if not need:
        return {"status": "fresh", "reason": ""}

    try:
        rows = _call_fetcher(table, start, end)
    except Exception as e:
        print(f"[FETCH FAIL] table={table}: {type(e).__name__}: {e}")
        if okno_coverage.okno_has_any_data(conn, table, start, end, cutoff=None):
            return {"status": "stale", "reason": "SOURCE_TIMEOUT"}
        return {"status": "no_data", "reason": "SOURCE_TIMEOUT"}

    if not rows:
        # источник ответил успешно, но событий в окне нет — это не отсутствие данных.
        return {"status": "fresh", "reason": "NO_EVENTS"}

    _upsert(table, conn, rows)
    return {"status": "fresh", "reason": "FETCH_SUCCESS"}


def _reason_for_score(score: Optional[float], fetch_status: Dict[str, str]) -> str:
    # reason_code для оценки, а не для фетча.
    if fetch_status.get("status") == "no_data":
        return fetch_status.get("reason", "NO_DATA")
    if score is None:
        # источник ответил, но по этому фактору событий нет — это не ошибка.
        return "NO_EVENTS"
    return "OK"


def okno_evaluate_core(
    data: Dict[str, Any],
    scores: Dict[str, Optional[float]],
    sources_status: Dict[str, Dict[str, str]],
    start: str,
    end: str,
    step_minutes: int,
    mode: str,
) -> Dict[str, Any]:
    warnings: List[str] = []

    # траектория
    trajectory_sample: List[dict] = []
    tle_rows = data.get("tle") or []
    if tle_rows:
        try:
            satrec = okno_trajectory.okno_build_satrec(tle_rows[0])
            if satrec is None:
                warnings.append("Failed to build Satrec from TLE")
            else:
                traj = okno_trajectory.okno_walk_window(satrec, start, end, step_minutes)
                trajectory_sample = traj[:3] if traj else []
        except Exception as e:
            warnings.append(f"Trajectory error: {e}")
    else:
        warnings.append("No TLE data")

    # overall score
    score_values = [v for v in scores.values() if isinstance(v, (int, float))]
    overall_score = sum(score_values) / len(score_values) if score_values else None

    # оценки по факторам
    space_weather = {
        "kp": {
            "score": scores.get("kp"),
            "reason_code": _reason_for_score(scores.get("kp"), sources_status.get("kp", {})),
        },
        "cme": {
            "score": scores.get("cme"),
            "reason_code": _reason_for_score(scores.get("cme"), sources_status.get("cme", {})),
        },
        "flr": {
            "score": scores.get("flr"),
            "reason_code": _reason_for_score(scores.get("flr"), sources_status.get("flr", {})),
        },
        "gst": {
            "score": scores.get("gst"),
            "reason_code": _reason_for_score(scores.get("gst"), sources_status.get("gst", {})),
        },
    }
    mmod = {
        "conjunctions": {
            "score": scores.get("conjunctions"),
            "reason_code": _reason_for_score(scores.get("conjunctions"), sources_status.get("conjunctions", {})),
        },
        "tle": {
            "score": scores.get("tle"),
            "reason_code": _reason_for_score(scores.get("tle"), sources_status.get("tle", {})),
        },
    }

    # warnings по отсутствующим источникам
    missing = [s for s, st in sources_status.items() if st.get("status") == "no_data"]
    if missing:
        warnings.append(f"No data for: {', '.join(missing)}")

    if overall_score is None:
        status = "insufficient_data"
    elif missing:
        status = "partial"
    else:
        status = "ok"

    return {
        "start": start,
        "end": end,
        "mode": mode,
        "step_minutes": step_minutes,
        "sources_status": sources_status,
        "trajectory_sample": trajectory_sample,
        "overall_score": overall_score,
        "space_weather": space_weather,
        "mmod": mmod,
        "warnings": warnings,
        "status": status,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def okno_evaluate_window(
    conn: Any,
    start: str,
    end: str,
    step_minutes: int = 10,
    mode: str = "current",
) -> Dict[str, Any]:
    cutoff = start if mode == "historical" else None

    sources_status: Dict[str, Dict[str, str]] = {}
    data: Dict[str, Any] = {}

    for table in SOURCES:
        sources_status[table] = okno_ensure_data(conn, table, start, end, mode)
        data[table] = _select(table, conn, start, end, cutoff)

    try:
        scores = okno_scoring.okno_score_all(data)
    except Exception as e:
        scores = {}
        sources_status["_scoring"] = {"status": "no_data", "reason": f"SCORING_ERROR: {e}"}

    return okno_evaluate_core(data, scores, sources_status, start, end, step_minutes, mode)


def okno_evaluate_from_dict(
    data: Dict[str, Any],
    start: str,
    end: str,
    step_minutes: int = 10,
) -> Dict[str, Any]:
    sources_status: Dict[str, Dict[str, str]] = {}
    for table in SOURCES:
        val = data.get(table)
        if val is not None and len(val) > 0:
            sources_status[table] = {"status": "fresh", "reason": "provided"}
        else:
            sources_status[table] = {"status": "no_data", "reason": "missing"}

    try:
        scores = okno_scoring.okno_score_all(data)
    except Exception as e:
        scores = {}
        sources_status["_scoring"] = {"status": "no_data", "reason": f"SCORING_ERROR: {e}"}

    return okno_evaluate_core(data, scores, sources_status, start, end, step_minutes, "current")


def okno_compare_windows(
    conn: Any,
    windows: List[Dict[str, str]],
    mode: str = "current",
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for w in windows:
        ev = okno_evaluate_window(conn, w["start"], w["end"], mode=mode)
        results.append({
            "id": w["id"],
            "overall_score": ev["overall_score"],
            "status": ev["status"],
            "warnings": ev["warnings"],
            # детализация по факторам — чтобы было видно, почему окно лучше.
            "space_weather": ev.get("space_weather", {}),
            "mmod": ev.get("mmod", {}),
        })

    valid = [
        r for r in results
        if r["status"] != "insufficient_data" and r["overall_score"] is not None
    ]

    if not valid:
        recommended = None
        explanation = "Недостаточно данных для рекомендации"
    else:
        # оценка -100..+100, где +100 = худший риск. Лучшее окно — минимальное.
        best = min(valid, key=lambda x: x["overall_score"])
        recommended = {"id": best["id"], "score": best["overall_score"]}

        parts = []
        for factor, d in best["space_weather"].items():
            score = d.get("score")
            if score is not None:
                parts.append(f"{factor}={score:.2f}")
        for factor, d in best["mmod"].items():
            score = d.get("score")
            if score is not None:
                parts.append(f"{factor}={score:.2f}")

        factor_str = ", ".join(parts) if parts else "нет данных по факторам"
        explanation = (
            f"Рекомендуется окно {best['id']} "
            f"(overall {best['overall_score']:.2f}; факторы: {factor_str})"
        )

    return {
        "windows": results,
        "recommended": recommended,
        "explanation": explanation,
    }
