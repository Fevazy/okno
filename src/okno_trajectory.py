# Copyright (c) 2026 Vasilyev Fyodor Mikhaylovich (aka Fevazy)
# SPDX-License-Identifier: Apache-2.0
import math
from datetime import datetime, timezone, timedelta
from sgp4.api import Satrec, jday


def _okno_gmst(jd: float) -> float:
    return (4.894961212735792 + 6.300388098984893 * (jd - 2451545.0)
            ) % (2.0 * math.pi)


OKNO_WGS84_A_KM = 6378.137
OKNO_WGS84_F = 1.0 / 298.257223563
OKNO_WGS84_E2 = OKNO_WGS84_F * (2.0 - OKNO_WGS84_F)


def _okno_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _okno_datetime_to_jd(dt: datetime) -> tuple[float, float]:
    u = _okno_to_utc(dt)
    sec = u.second + u.microsecond * 1e-6
    return jday(u.year, u.month, u.day, u.hour, u.minute, sec)


def _okno_eci_to_geodetic(
    x: float, y: float, z: float, jd: float, fr: float
) -> tuple[float, float, float]:
    # TEME -> ECEF через GMST, затем ECEF -> геодезия (Bowring fixed-point).
    gmst = _okno_gmst(jd + fr)
    cg = math.cos(gmst)
    sg = math.sin(gmst)
    xe = x * cg + y * sg
    ye = -x * sg + y * cg
    ze = z

    a = OKNO_WGS84_A_KM
    e2 = OKNO_WGS84_E2
    b = a * math.sqrt(1.0 - e2)

    p = math.hypot(xe, ye)
    lon = math.atan2(ye, xe)

    if p < 1e-9:
        lat = math.copysign(math.pi / 2.0, ze)
        alt = abs(ze) - b
        return math.degrees(lat), math.degrees(lon), alt

    lat = math.atan2(ze, p * (1.0 - e2))
    alt = 0.0
    for _ in range(10):
        s = math.sin(lat)
        n = a / math.sqrt(1.0 - e2 * s * s)
        alt = p / math.cos(lat) - n
        lat_new = math.atan2(ze, p * (1.0 - e2 * n / (n + alt)))
        if abs(lat_new - lat) < 1e-12:
            lat = lat_new
            break
        lat = lat_new

    s = math.sin(lat)
    n = a / math.sqrt(1.0 - e2 * s * s)
    alt = p / math.cos(lat) - n

    return math.degrees(lat), math.degrees(lon), alt


def okno_build_satrec(tle_row: dict) -> Satrec | None:
    line1 = tle_row.get("line1")
    line2 = tle_row.get("line2")
    if not line1 or not line2:
        return None
    return Satrec.twoline2rv(line1, line2)


def okno_get_position(sat: Satrec, dt: datetime) -> dict:
    jd, fr = _okno_datetime_to_jd(dt)
    # sgp4 возвращает (error, r, v); r — кортеж (x, y, z) в км TEME.
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        return {"lat": 0.0, "lon": 0.0, "alt_km": 0.0, "ok": False,
                "error": str(e)}
    x, y, z = r
    lat, lon, alt = _okno_eci_to_geodetic(x, y, z, jd, fr)
    return {"lat": lat, "lon": lon, "alt_km": alt, "ok": True, "error": None}


def okno_walk_window(
    sat: Satrec, start: str, end: str, step_minutes: int = 10
) -> list[dict]:
    if step_minutes <= 0:
        raise ValueError("step_minutes must be positive")

    t_start = _okno_to_utc(datetime.fromisoformat(start))
    t_end = _okno_to_utc(datetime.fromisoformat(end))
    step = timedelta(minutes=step_minutes)

    out: list[dict] = []
    t = t_start
    while t <= t_end:
        pos = okno_get_position(sat, t)
        out.append(
            {
                "time": t.isoformat(),
                "lat": pos["lat"],
                "lon": pos["lon"],
                "alt_km": pos["alt_km"],
                "ok": pos["ok"],
            }
        )
        t = t + step
    return out
