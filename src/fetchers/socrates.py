from datetime import datetime, timezone
import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_tags(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "<":
            j = s.find(">", i)
            if j == -1:
                break
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out).strip()


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    t = s.strip()
    if not t or t in {"-", "N/A", "n/a", "null"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def okno_fetch_conjunctions(norad_id: int = 25544, days_ahead: int = 2
                            ) -> list[dict]:
    url = (
        "https://celestrak.org/SOCRATES/table-socrates.php"
        f"?CATNR={norad_id}&MAX={days_ahead * 24}"
    )
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"celestrak socrates: HTTP {r.status_code}")

    # SOCRATES отдаёт HTML, а не JSON, парсим вручную.
    html = r.text.replace("<th>", "<td>").replace("</th>", "</td>")

    rows: list[list[str]] = []
    for raw in html.split("<tr>"):
        cells_raw = raw.split("<td>")
        if len(cells_raw) < 2:
            continue
        cells = [_strip_tags(c.split("</td>")[0]) for c in cells_raw[1:]]
        if cells:
            rows.append(cells)

    if len(rows) < 2:
        raise RuntimeError("celestrak socrates: parse failed")

    header = [c.upper() for c in rows[0]]
    idx = {name: i for i, name in enumerate(header)}

    def pick(row: list[str], *names: str) -> str | None:
        for n in names:
            if n in idx:
                i = idx[n]
                if i < len(row):
                    return row[i]
        return None

    fetched_at = _now()
    out: list[dict] = []

    for row in rows[1:]:
        tca = pick(row, "TCA")
        if not tca:
            continue
        out.append({
            "norad_id": norad_id,
            # SOCRATES называет колонку SAT_NAME; остальные варианты — запасные
            "object_name": pick(row, "SAT_NAME", "SATNAME", "OBJECT_NAME",
                                "NAME"),
            "tca": tca,
            "min_range_km": _to_float(pick(row, "TCA_RANGE", "MIN_RANGE_KM",
                                           "MIN_RANGE")),
            "rel_speed_km_s": _to_float(pick(row, "TCA_RELATIVE_SPEED",
                                             "REL_SPEED_KM_S", "REL_SPEED")),
            "probability": _to_float(pick(row, "MAX_PROB", "PROBABILITY")),
            "published_at": tca,
            "fetched_at": fetched_at,
            "source": "celestrak_socrates",
        })

    if not out:
        raise RuntimeError("celestrak socrates: parse failed")

    return out
