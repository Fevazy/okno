import os
from datetime import datetime, timezone
import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(s: str | None) -> str | None:
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _get(path: str, start_date: str, end_date: str) -> list[dict]:
    key = os.getenv("NASA_API_KEY", "DEMO_KEY")
    url = (
        f"https://api.nasa.gov/DONKI/{path}"
        f"?startDate={start_date}&endDate={end_date}&api_key={key}"
    )
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"nasa donki {path}: HTTP {r.status_code}")
    data = r.json()
    if data is None:
        return []
    if not isinstance(data, list):
        raise RuntimeError(f"nasa donki {path}: unexpected payload")
    return data


def okno_fetch_cme(start_date: str, end_date: str) -> list[dict]:
    items = _get("CME", start_date, end_date)
    fetched_at = _now()
    out: list[dict] = []

    for item in items:
        start_time = _iso(item.get("startTime"))
        analyses = item.get("cmeAnalyses") or []
        speed = None
        half_angle = None
        cme_type = None
        if analyses:
            a0 = analyses[0]
            speed = a0.get("speed")
            half_angle = a0.get("halfAngle")
            cme_type = a0.get("type")
        out.append({
            "id": item.get("activityID"),
            "start_time": start_time,
            "speed": speed,
            "half_angle": half_angle,
            "type": cme_type,
            # DONKI не отдаёт момент публикации записи; используем startTime
            # как аппроксимацию. Для strict replay это ограничение надо
            # указывать в limitations.
            "published_at": start_time,
            "fetched_at": fetched_at,
            "source": "nasa_donki",
        })

    return out


def okno_fetch_flr(start_date: str, end_date: str) -> list[dict]:
    items = _get("FLR", start_date, end_date)
    fetched_at = _now()
    out: list[dict] = []

    for item in items:
        begin_time = _iso(item.get("beginTime"))
        peak_time = _iso(item.get("peakTime"))
        out.append({
            "id": item.get("flrID"),
            "begin_time": begin_time,
            "peak_time": peak_time,
            "class": item.get("classType"),
            # см. комментарий в okno_fetch_cme про published_at
            "published_at": begin_time,
            "fetched_at": fetched_at,
            "source": "nasa_donki",
        })

    return out


def okno_fetch_gst(start_date: str, end_date: str) -> list[dict]:
    items = _get("GST", start_date, end_date)
    fetched_at = _now()
    out: list[dict] = []

    for item in items:
        start_time = _iso(item.get("startTime"))
        kp_list = item.get("allKpIndex") or []
        kp_index = kp_list[0].get("kpIndex") if kp_list else None
        out.append({
            "id": item.get("gstID"),
            "start_time": start_time,
            "kp_index": kp_index,
            # см. комментарий в okno_fetch_cme про published_at
            "published_at": start_time,
            "fetched_at": fetched_at,
            "source": "nasa_donki",
        })

    return out
