import sqlite3

OKNO_DB_PATH = "okno.db"


def okno_open(path: str = OKNO_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def okno_init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tle (
            id INTEGER PRIMARY KEY,
            norad_id INTEGER,
            epoch TEXT,
            line1 TEXT,
            line2 TEXT,
            fetched_at TEXT,
            source TEXT,
            UNIQUE(norad_id, epoch)
        );

        CREATE TABLE IF NOT EXISTS kp (
            time TEXT,
            kp REAL,
            published_at TEXT,
            fetched_at TEXT,
            source TEXT,
            PRIMARY KEY(time, source)
        );

        CREATE TABLE IF NOT EXISTS cme (
            id TEXT PRIMARY KEY,
            start_time TEXT,
            speed REAL,
            half_angle REAL,
            type TEXT,
            published_at TEXT,
            fetched_at TEXT,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS flr (
            id TEXT PRIMARY KEY,
            begin_time TEXT,
            peak_time TEXT,
            class TEXT,
            published_at TEXT,
            fetched_at TEXT,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS gst (
            id TEXT PRIMARY KEY,
            start_time TEXT,
            kp_index REAL,
            published_at TEXT,
            fetched_at TEXT,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS conjunctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            norad_id INTEGER,
            object_name TEXT,
            tca TEXT,
            min_range_km REAL,
            rel_speed_km_s REAL,
            probability REAL,
            published_at TEXT,
            fetched_at TEXT,
            source TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS conjunctions_natural_key
        ON conjunctions(norad_id, tca, object_name, source);
        """
    )
    conn.commit()


def okno_upsert_kp(conn: sqlite3.Connection, rows: list[dict]) -> int:
    # SQLite ON CONFLICT требует уникального индекса, см. схему.
    conn.executemany(
        """
        INSERT INTO kp (time, kp, published_at, fetched_at, source)
        VALUES (:time, :kp, :published_at, :fetched_at, :source)
        ON CONFLICT(time, source) DO UPDATE SET
            kp = excluded.kp,
            published_at = excluded.published_at,
            fetched_at = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def okno_upsert_tle(conn: sqlite3.Connection, rows: list[dict]) -> int:
    # SQLite ON CONFLICT требует уникального индекса, см. схему.
    conn.executemany(
        """
        INSERT INTO tle (norad_id, epoch, line1, line2, fetched_at, source)
        VALUES (:norad_id, :epoch, :line1, :line2, :fetched_at, :source)
        ON CONFLICT(norad_id, epoch) DO UPDATE SET
            line1 = excluded.line1,
            line2 = excluded.line2,
            fetched_at = excluded.fetched_at,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def okno_upsert_cme(conn: sqlite3.Connection, rows: list[dict]) -> int:
    # SQLite ON CONFLICT требует уникального индекса, см. схему.
    conn.executemany(
        """
        INSERT INTO cme (id, start_time, speed, half_angle, type, published_at,
            fetched_at, source)
        VALUES (:id, :start_time, :speed, :half_angle, :type, :published_at,
            :fetched_at, :source)
        ON CONFLICT(id) DO UPDATE SET
            start_time = excluded.start_time,
            speed = excluded.speed,
            half_angle = excluded.half_angle,
            type = excluded.type,
            published_at = excluded.published_at,
            fetched_at = excluded.fetched_at,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def okno_upsert_flr(conn: sqlite3.Connection, rows: list[dict]) -> int:
    # SQLite ON CONFLICT требует уникального индекса, см. схему.
    conn.executemany(
        """
        INSERT INTO flr (id, begin_time, peak_time, class, published_at,
            fetched_at, source)
        VALUES (:id, :begin_time, :peak_time, :class, :published_at,
            :fetched_at, :source)
        ON CONFLICT(id) DO UPDATE SET
            begin_time = excluded.begin_time,
            peak_time = excluded.peak_time,
            class = excluded.class,
            published_at = excluded.published_at,
            fetched_at = excluded.fetched_at,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def okno_upsert_gst(conn: sqlite3.Connection, rows: list[dict]) -> int:
    # SQLite ON CONFLICT требует уникального индекса, см. схему.
    conn.executemany(
        """
        INSERT INTO gst (id, start_time, kp_index, published_at, fetched_at,
            source)
        VALUES (:id, :start_time, :kp_index, :published_at, :fetched_at,
            :source)
        ON CONFLICT(id) DO UPDATE SET
            start_time = excluded.start_time,
            kp_index = excluded.kp_index,
            published_at = excluded.published_at,
            fetched_at = excluded.fetched_at,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def okno_upsert_conjunctions(conn: sqlite3.Connection,
                             rows: list[dict]) -> int:

    # SQLite ON CONFLICT требует уникального индекса, см. схему.
    conn.executemany(
        """
        INSERT INTO conjunctions (
            norad_id, object_name, tca, min_range_km, rel_speed_km_s,
            probability, published_at, fetched_at, source
        )
        VALUES (
            :norad_id, :object_name, :tca, :min_range_km, :rel_speed_km_s,
            :probability, :published_at, :fetched_at, :source
        )
        ON CONFLICT(norad_id, tca, object_name, source) DO UPDATE SET
            min_range_km = excluded.min_range_km,
            rel_speed_km_s = excluded.rel_speed_km_s,
            probability = excluded.probability,
            published_at = excluded.published_at,
            fetched_at = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def okno_select_kp(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    cutoff: str | None = None,
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT time, kp, published_at, source
        FROM kp
        WHERE time BETWEEN ? AND ?
          AND (? IS NULL OR published_at <= ?)
        ORDER BY time
        """,
        (start, end, cutoff, cutoff),
    )
    return [dict(row) for row in cur.fetchall()]


def okno_select_cme(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    cutoff: str | None = None,
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, start_time, speed, half_angle, type, published_at, source
        FROM cme
        WHERE start_time BETWEEN ? AND ?
          AND (? IS NULL OR published_at <= ?)
        ORDER BY start_time
        """,
        (start, end, cutoff, cutoff),
    )
    return [dict(row) for row in cur.fetchall()]


def okno_select_flr(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    cutoff: str | None = None,
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, begin_time, peak_time, class, published_at, source
        FROM flr
        WHERE begin_time BETWEEN ? AND ?
          AND (? IS NULL OR published_at <= ?)
        ORDER BY begin_time
        """,
        (start, end, cutoff, cutoff),
    )
    return [dict(row) for row in cur.fetchall()]


def okno_select_gst(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    cutoff: str | None = None,
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, start_time, kp_index, published_at, source
        FROM gst
        WHERE start_time BETWEEN ? AND ?
          AND (? IS NULL OR published_at <= ?)
        ORDER BY start_time
        """,
        (start, end, cutoff, cutoff),
    )
    return [dict(row) for row in cur.fetchall()]


def okno_select_conjunctions(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    cutoff: str | None = None,
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, norad_id, object_name, tca, min_range_km, rel_speed_km_s,
               probability, published_at, source
        FROM conjunctions
        WHERE tca BETWEEN ? AND ?
          AND (? IS NULL OR published_at <= ?)
        ORDER BY tca
        """,
        (start, end, cutoff, cutoff),
    )
    return [dict(row) for row in cur.fetchall()]


def okno_select_latest_tle(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        """
        SELECT t.id, t.norad_id, t.epoch, t.line1, t.line2, t.fetched_at,
            t.source
        FROM tle AS t
        INNER JOIN (
            SELECT norad_id, MAX(epoch) AS max_epoch
            FROM tle
            GROUP BY norad_id
        ) AS m
        ON t.norad_id = m.norad_id AND t.epoch = m.max_epoch
        ORDER BY t.norad_id
        """
    )
    return [dict(row) for row in cur.fetchall()]


def okno_close(conn: sqlite3.Connection) -> None:
    conn.close()
