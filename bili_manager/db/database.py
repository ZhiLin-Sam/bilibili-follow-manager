"""SQLite 数据库 — 关注数据持久化"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

from ..utils.helpers import logger, get_data_dir

DB_PATH = get_data_dir() / "bili_follows.db"


def get_conn() -> sqlite3.Connection:
    get_data_dir().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS follows (
            mid      INTEGER PRIMARY KEY,
            uname    TEXT,
            sign     TEXT,
            face     TEXT,
            mtime    INTEGER,
            official_verify_type INTEGER DEFAULT 0,
            official_verify_desc TEXT DEFAULT '',
            vip_status  INTEGER DEFAULT 0,
            vip_type    INTEGER DEFAULT 0,
            raw_json    TEXT DEFAULT '' -- 原始 API 返回
        );

        CREATE TABLE IF NOT EXISTS probes (
            mid           INTEGER PRIMARY KEY,
            archive_count INTEGER DEFAULT -1,
            video_count   INTEGER DEFAULT -1,
            follower      INTEGER DEFAULT -1,
            following     INTEGER DEFAULT -1,
            like_num      INTEGER DEFAULT -1,
            total_view    INTEGER DEFAULT -1,
            total_likes   INTEGER DEFAULT -1,
            level         INTEGER DEFAULT -1,
            spacesta      INTEGER DEFAULT -999,
            ff_ratio      REAL DEFAULT 0.0,
            probe_time    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS verdicts (
            mid            INTEGER PRIMARY KEY,
            verdict        TEXT DEFAULT 'unreviewed',  -- keep / delete / unreviewed / skip
            rule_keep      TEXT DEFAULT '',
            rule_delete    TEXT DEFAULT '',
            rule_probe     TEXT DEFAULT '',
            keep_score     INTEGER DEFAULT 0,
            delete_score   INTEGER DEFAULT 0,
            reviewed_at    TEXT DEFAULT '',
            note           TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_verdicts_verdict ON verdicts(verdict);
        CREATE INDEX IF NOT EXISTS idx_probes_spacesta ON probes(spacesta);
    """)
    conn.commit()
    conn.close()
    logger.info("数据库初始化完成")


def save_follows(follows: list[dict]) -> int:
    """保存关注列表, 返回新增/更新数量"""
    conn = get_conn()
    count = 0
    for f in follows:
        conn.execute("""
            INSERT OR REPLACE INTO follows
                (mid, uname, sign, face, mtime, official_verify_type,
                 official_verify_desc, vip_status, vip_type, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["mid"], f["uname"], f.get("sign", ""), f.get("face", ""),
            f.get("mtime", 0),
            f.get("official_verify", {}).get("type", 0) if isinstance(f.get("official_verify"), dict) else 0,
            f.get("official_verify", {}).get("desc", "") if isinstance(f.get("official_verify"), dict) else "",
            f.get("vip", {}).get("vipStatus", 0) if isinstance(f.get("vip"), dict) else 0,
            f.get("vip", {}).get("vipType", 0) if isinstance(f.get("vip"), dict) else 0,
            json.dumps(f, ensure_ascii=False)
        ))
        count += 1
    conn.commit()
    conn.close()
    return count


def save_probes(probes: list[dict]) -> int:
    conn = get_conn()
    now = datetime.now().isoformat()
    count = 0
    for p in probes:
        conn.execute("""
            INSERT OR REPLACE INTO probes
                (mid, archive_count, video_count, follower, following,
                 like_num, total_view, total_likes, level, spacesta, ff_ratio, probe_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["uid"], p.get("archive_count", -1), p.get("video_count", -1),
            p.get("follower", -1), p.get("following", -1),
            p.get("like_num", -1), p.get("total_view", -1), p.get("total_likes", -1),
            p.get("level", -1), p.get("spacesta", -999), p.get("ff_ratio", 0.0), now
        ))
        count += 1
    conn.commit()
    conn.close()
    return count


def save_verdicts(verdicts: list[dict]) -> int:
    conn = get_conn()
    now = datetime.now().isoformat()
    count = 0
    for v in verdicts:
        conn.execute("""
            INSERT OR REPLACE INTO verdicts
                (mid, verdict, rule_keep, rule_delete, rule_probe,
                 keep_score, delete_score, reviewed_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            v["mid"], v.get("verdict", "unreviewed"),
            v.get("rule_keep", ""), v.get("rule_delete", ""), v.get("rule_probe", ""),
            v.get("keep_score", 0), v.get("delete_score", 0),
            now, v.get("note", "")
        ))
        count += 1
    conn.commit()
    conn.close()
    return count


def get_all_with_verdicts(verdict_filter: str | None = None) -> list[dict]:
    conn = get_conn()
    query = """
        SELECT f.*,
               p.archive_count, p.video_count, p.follower as probe_follower,
               p.following, p.like_num, p.total_view, p.total_likes,
               p.level, p.spacesta, p.ff_ratio,
               v.verdict, v.rule_keep, v.rule_delete, v.rule_probe,
               v.keep_score, v.delete_score, v.note
        FROM follows f
        LEFT JOIN probes p ON f.mid = p.mid
        LEFT JOIN verdicts v ON f.mid = v.mid
    """
    params = []
    if verdict_filter:
        query += " WHERE v.verdict = ?"
        params.append(verdict_filter)
    query += " ORDER BY v.delete_score DESC, p.spacesta ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_stats() -> dict:
    conn = get_conn()
    stats = {}
    row = conn.execute("SELECT COUNT(*) as cnt FROM follows").fetchone()
    stats["total_follows"] = row["cnt"]
    row = conn.execute("SELECT COUNT(*) as cnt FROM probes").fetchone()
    stats["total_probes"] = row["cnt"]
    for v in ("keep", "delete", "unreviewed"):
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM verdicts WHERE verdict = ?", (v,)
        ).fetchone()
        stats[f"verdict_{v}"] = row["cnt"]
    conn.close()
    return stats


def get_follow_uids(verdict_filter: str | None = None) -> list[int]:
    conn = get_conn()
    query = "SELECT f.mid FROM follows f"
    params = []
    if verdict_filter:
        query += " JOIN verdicts v ON f.mid = v.mid WHERE v.verdict = ?"
        params.append(verdict_filter)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [row["mid"] for row in rows]
