from datetime import datetime, timezone
import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(time_tag: str) -> str:
    # NOAA отдаёт "2026-09-18 12:00:00.000" или "2026-09-18T12:00:00Z".
    # Приводим к канонической форме с +00:00.
    s = time_tag.strip().replace(" ", "T").replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def okno_fetch_kp() -> list[dict]:
    url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"noaa swpc kp: HTTP {r.status_code}")

    data = r.json()
    if not data:
        return []

    fetched_at = _now()
    out: list[dict] = []

    if isinstance(data[0], dict):
        # новая схема: массив объектов с ключами
        for item in data:
            t = _iso(str(item["time_tag"]))
            out.append({
                "time": t,
                "kp": float(item["estimated_kp"]),
                "published_at": t,
                "fetched_at": fetched_at,
                "source": "noaa_swpc",
            })
    else:
        # старая схема: массив массивов, первая строка — заголовки
        for row in data[1:]:
            t = _iso(str(row[0]))
            out.append({
                "time": t,
                "kp": float(row[1]),
                "published_at": t,
                "fetched_at": fetched_at,
                "source": "noaa_swpc",
            })

    return out
