from datetime import datetime, timedelta, timezone
import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def okno_fetch_tle(norad_id: int = 25544) -> list[dict]:
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"celestrak tle: HTTP {r.status_code}")

    lines = [ln.strip() for ln in r.text.splitlines() if ln.strip()]
    if len(lines) < 3:
        raise RuntimeError("celestrak tle: unexpected payload")

    fetched_at = _now()
    out: list[dict] = []

    i = 0
    while i + 2 < len(lines):
        line1 = lines[i + 1]
        line2 = lines[i + 2]
        if not line1.startswith("1 ") or not line2.startswith("2 "):
            # если первый блок не TLE — возможно, файл в другом формате
            raise RuntimeError("celestrak tle: bad line prefix")

        # epoch в TLE — year+day-of-year, см. формат NORAD.
        yy = int(line1[18:20])
        year = 2000 + yy if yy < 57 else 1900 + yy
        doy = float(line1[20:32])
        epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1.0)

        out.append({
            "norad_id": norad_id,
            "epoch": epoch.isoformat(),
            "line1": line1,
            "line2": line2,
            "fetched_at": fetched_at,
            "source": "celestrak",
        })
        i += 3

    if not out:
        raise RuntimeError("celestrak tle: no entries parsed")

    return out
