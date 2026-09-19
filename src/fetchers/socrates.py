from datetime import datetime, timezone
import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_tags(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        if s[i] == "<":
            j = s.find(">", i)
            if j == -1:
                break
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out).strip()


def _to_float(s):
    if s is None:
        return None
    t = s.strip()
    if not t or t in {"-", "N/A", "n/a", "null"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def okno_fetch_conjunctions(norad_id: int = 25544, days_ahead: int = 2) -> list[dict]:
    url = (
        "https://celestrak.org/SOCRATES/table-socrates.php"
        f"?CATNR={norad_id}&MAX={days_ahead * 24}"
    )
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"celestrak socrates: HTTP {r.status_code}")

    html = r.text
    if "<html" not in html.lower() and "<!doctype" not in html.lower():
        # если когда-нибудь переедут на CSV — увидим это в логе.
        raise RuntimeError("celestrak socrates: expected HTML page")

    # SOCRATES отдаёт HTML-таблицу; парсим вручную, без bs4.
    html2 = html.replace("<th>", "<td>").replace("</th>", "</td>")
    rows: list[list[str]] = []
    for raw in html2.split("<tr>"):
        cells_raw = raw.split("<td>")
        if len(cells_raw) < 2:
            continue
        cells = [_strip_tags(c.split("</td>")[0]) for c in cells_raw[1:]]
        if cells:
            rows.append(cells)

    if len(rows) < 2:
        # нет строк данных — это не ошибка, просто нет сближений
        return []

    header = [c.upper() for c in rows[0]]
    idx = {name: i for i, name in enumerate(header)}

    def pick(row, *names):
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
            "object_name": pick(row, "NAME", "SAT_NAME", "OBJECT_NAME"),
            "tca": tca,
            "min_range_km": _to_float(pick(row, "MIN RANGE (KM)", "TCA_RANGE", "MIN_RANGE_KM")),
            "rel_speed_km_s": _to_float(pick(row, "RELATIVE SPEED (KM/SEC)", "TCA_RELATIVE_SPEED", "REL_SPEED_KM_S")),
            "probability": _to_float(pick(row, "MAX PROBABILITY", "MAX_PROB", "PROBABILITY")),
            "published_at": tca,
            "fetched_at": fetched_at,
            "source": "celestrak_socrates",
        })

    return out
