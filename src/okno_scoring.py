# Copyright (c) 2026 Vasilyev Fyodor Mikhaylovich (aka Fevazy)
# SPDX-License-Identifier: Apache-2.0
def okno_lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def okno_clamp(v: float, lo: float = -100.0, hi: float = 100.0) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def okno_worst(values: list[float | None]) -> float | None:
    best = None
    for v in values:
        if v is None:
            continue
        if best is None or v > best:
            best = v
    return best


def okno_scale_by(value: float, mult: float) -> float:
    # множитель должен усиливать риск, а не инвертировать знак:
    # для положительных — умножаем, для отрицательных — делим.
    if value >= 0.0:
        return value * mult
    if mult == 0.0:
        return value
    return value / mult


def okno_score_kp(kp: float | None) -> float | None:
    if kp is None:
        return None
    kp = okno_clamp(kp, 0.0, 9.0)
    points = [
        (0.0, -100.0),
        (1.0, -66.0),
        (2.0, -33.0),
        (3.0, 0.0),
        (4.0, 0.0),
        (5.0, 30.0),
        (6.0, 55.0),
        (7.0, 75.0),
        (8.0, 90.0),
        (9.0, 100.0),
    ]
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if kp <= x1:
            return okno_lerp(kp, x0, x1, y0, y1)
    return 100.0


def okno_score_cme(speed_km_s: float | None, half_angle_deg: float | None
                   ) -> float | None:
    if speed_km_s is None:
        return None
    s = speed_km_s
    if s < 250.0:
        base = okno_lerp(s, 0.0, 250.0, -100.0, -50.0)
    elif s < 500.0:
        base = okno_lerp(s, 250.0, 500.0, -50.0, 0.0)
    elif s < 1000.0:
        base = okno_lerp(s, 500.0, 1000.0, 0.0, 40.0)
    elif s < 2000.0:
        base = okno_lerp(s, 1000.0, 2000.0, 40.0, 80.0)
    else:
        # наблюдаемые скорости CME до ~3000 км/с, на 3000 насыщаемся в +100.
        base = okno_lerp(s, 2000.0, 3000.0, 80.0, 100.0)

    if half_angle_deg is None:
        mult = 1.0
    elif half_angle_deg < 30.0:
        mult = 0.5
    elif half_angle_deg <= 90.0:
        mult = 0.75
    else:
        mult = 1.0

    return okno_clamp(okno_scale_by(base, mult), -100.0, 100.0)


def okno_score_flr(class_type: str | None) -> float | None:
    if class_type is None:
        return None
    s = class_type.strip().upper()
    if not s:
        return None
    c = s[0]
    if c not in "ABCMX":
        return None

    if len(s) == 1:
        v = 1.0
    else:
        try:
            v = float(s[1:])
        except ValueError:
            return None

    v = okno_clamp(v, 0.0, 10.0)

    if c == "A":
        return okno_lerp(v, 0.0, 10.0, -100.0, -80.0)
    if c == "B":
        return okno_lerp(v, 0.0, 10.0, -80.0, -50.0)
    if c == "C":
        return okno_lerp(v, 0.0, 10.0, -50.0, 0.0)
    if c == "M":
        return okno_lerp(v, 0.0, 10.0, 0.0, 50.0)
    return okno_lerp(v, 0.0, 10.0, 50.0, 100.0)


def okno_score_gst(kp_index: float | None) -> float | None:
    if kp_index is None:
        return None
    kp = okno_clamp(kp_index, 0.0, 9.0)
    if kp < 5.0:
        return okno_lerp(kp, 0.0, 5.0, -100.0, 0.0)

    points = [
        (5.0, 20.0),
        (6.0, 40.0),
        (7.0, 60.0),
        (8.0, 80.0),
        (9.0, 100.0),
    ]
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if kp <= x1:
            return okno_lerp(kp, x0, x1, y0, y1)
    return 100.0


def okno_score_conjunction(
    min_range_km: float | None,
    probability: float | None,
    rel_speed_km_s: float | None,
) -> float | None:
    if min_range_km is None:
        return None

    mr = min_range_km
    if mr < 1.0:
        r = okno_clamp(mr, 0.0, 1.0)
        base = okno_lerp(r, 0.0, 1.0, 100.0, 80.0)
    elif mr < 5.0:
        base = okno_lerp(mr, 1.0, 5.0, 80.0, 40.0)
    elif mr < 10.0:
        base = okno_lerp(mr, 5.0, 10.0, 40.0, 0.0)
    elif mr <= 50.0:
        base = okno_lerp(mr, 10.0, 50.0, 0.0, -50.0)
    else:
        r = okno_clamp(mr, 50.0, 100.0)
        base = okno_lerp(r, 50.0, 100.0, -50.0, -100.0)

    if probability is not None:
        if probability > 0.01:
            base += 40.0
        elif probability > 0.001:
            base += 20.0

    if rel_speed_km_s is not None:
        if rel_speed_km_s > 10.0:
            base = okno_scale_by(base, 1.2)
        elif rel_speed_km_s < 1.0:
            base = okno_scale_by(base, 0.8)

    return okno_clamp(base, -100.0, 100.0)


def _okno_score_kp_list(rows: list[dict] | None) -> float | None:
    if not rows:
        return None
    return okno_worst([okno_score_kp(r.get("kp")) for r in rows])


def _okno_score_cme_list(rows: list[dict] | None) -> float | None:
    if not rows:
        return None
    return okno_worst([okno_score_cme(r.get("speed"),
                                      r.get("half_angle")) for r in rows])


def _okno_score_flr_list(rows: list[dict] | None) -> float | None:
    if not rows:
        return None
    return okno_worst([okno_score_flr(r.get("class")) for r in rows])


def _okno_score_gst_list(rows: list[dict] | None) -> float | None:
    if not rows:
        return None
    return okno_worst([okno_score_gst(r.get("kp_index")) for r in rows])


def _okno_score_conj_list(rows: list[dict] | None) -> float | None:
    if not rows:
        return None
    return okno_worst([
        okno_score_conjunction(
            r.get("min_range_km"),
            r.get("probability"),
            r.get("rel_speed_km_s"),
        )
        for r in rows
    ])


def okno_score_all(data: dict | None) -> dict[str, float | None]:
    if data is None:
        data = {}
    return {
        "kp": _okno_score_kp_list(data.get("kp")),
        "cme": _okno_score_cme_list(data.get("cme")),
        "flr": _okno_score_flr_list(data.get("flr")),
        "gst": _okno_score_gst_list(data.get("gst")),
        "conjunctions": _okno_score_conj_list(data.get("conjunctions")),
        "tle": None,
    }
