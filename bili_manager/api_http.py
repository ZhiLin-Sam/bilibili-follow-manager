"""FastAPI HTTP API — React 前端后端 (端口 9000)"""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from contextlib import suppress as contextlib_suppress
from io import BytesIO

import qrcode
import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .api.account import batch_probe
from .api.client import BiliClient
from .api.following import fetch_all_followings
from .api.unfollow import batch_unfollow
from .auth.login import (
    HEADERS,
    QR_GENERATE_URL,
    QR_POLL_URL,
    load_cookies,
    save_cookies,
)
from .db import database
from .rules.engine import RuleEngine
from .utils.helpers import logger

# ── State ───────────────────────────────────────────────────
_app_client: BiliClient | None = None
_app_engine = RuleEngine()
_stop_flags: dict[str, bool] = {}
_probe_progress: dict = {"current": 0, "total": 0, "running": False}


def get_client() -> BiliClient:
    if _app_client is None:
        raise HTTPException(401, "Not logged in")
    return _app_client


# ── Lifespan ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    # Try loading cached cookies
    global _app_client
    cookies = load_cookies()
    if cookies and "SESSDATA" in cookies:
        _app_client = BiliClient(cookies)
        logger.info("Loaded cached cookies")
    yield


app = FastAPI(lifespan=lifespan, title="BiliManager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth ────────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    """Return login state + database stats."""
    global _app_client
    stats = {}
    with contextlib_suppress(Exception):
        stats = database.get_stats()
    return {
        "logged_in": _app_client is not None,
        "uid": _app_client.uid if _app_client else "",
        "stats": stats,
    }


@app.post("/api/login/qrcode")
def login_qrcode():
    """Generate QR login URL + key. Returns QR PNG bytes + key."""
    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(QR_GENERATE_URL)
    if resp.status_code != 200:
        raise HTTPException(500, f"QR generate failed: {resp.status_code}")
    data = resp.json()
    if data.get("code") != 0:
        raise HTTPException(500, f"B站API错误: {data}")
    qrcode_key = data["data"]["qrcode_key"]
    qr_url = data["data"]["url"]

    # Generate QR PNG
    qr = qrcode.QRCode(box_size=5, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)

    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"X-Qrcode-Key": qrcode_key})


@app.post("/api/login/poll/{qrcode_key}")
def login_poll(qrcode_key: str):
    """Poll QR scan status. Returns {status, cookies?}"""
    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(QR_POLL_URL, params={"qrcode_key": qrcode_key})
    data = resp.json()
    code = data.get("data", {}).get("code", -1)

    if code == 0:
        # Success — extract cookies
        cookies = {}
        for c in session.cookies:
            cookies[c.name] = c.value
        with contextlib_suppress(ValueError):
            cookies["DedeUserID"] = str(int(cookies.get("DedeUserID", "")))
        save_cookies(cookies)
        global _app_client
        _app_client = BiliClient(cookies)
        return {"status": "success", "uid": cookies.get("DedeUserID", "")}
    elif code == 86038:
        return {"status": "expired"}
    elif code == 86090:
        return {"status": "scanned"}
    elif code == 86101:
        return {"status": "waiting"}
    else:
        return {"status": "error", "message": data.get("data", {}).get("message", str(code))}


@app.post("/api/login/cookie")
def login_cookie():
    """Load cached cookies."""
    global _app_client
    cookies = load_cookies()
    if not cookies or "SESSDATA" not in cookies:
        raise HTTPException(400, "无有效缓存 Cookie")
    _app_client = BiliClient(cookies)
    return {"uid": _app_client.uid}


@app.post("/api/login/logout")
def login_logout():
    global _app_client
    _app_client = None
    return {"ok": True}


# ── Follows ─────────────────────────────────────────────────

@app.post("/api/follows/fetch")
async def fetch_follows():
    """SSE streaming: fetch all followings with progress."""
    client = get_client()
    _stop_flags["fetch"] = False

    async def event_generator():
        try:
            def progress_cb(pg, total, count):
                pass  # handled in thread

            result_container = {"follows": [], "total": 0, "error": None}

            def _run():
                try:
                    follows, total = fetch_all_followings(client, progress_callback=None)
                    result_container["follows"] = follows
                    result_container["total"] = total
                except Exception as e:
                    result_container["error"] = str(e)

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

            # Poll for completion, yielding SSE progress
            while thread.is_alive():
                if _stop_flags.get("fetch"):
                    _stop_flags["fetch"] = False
                    yield f"data: {json.dumps({'done': True, 'stopped': True})}\n\n"
                    return
                await asyncio.sleep(0.5)
                yield f"data: {json.dumps({'progress': 0, 'text': '拉取中...'})}\n\n"

            thread.join()

            if result_container["error"]:
                yield f"data: {json.dumps({'done': True, 'error': result_container['error']})}\n\n"
                return

            follows, total = result_container["follows"], result_container["total"]
            database.save_follows(follows)
            yield f"data: {json.dumps({'done': True, 'count': len(follows), 'total': total})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'done': True, 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/follows/fetch/stop")
def fetch_stop():
    _stop_flags["fetch"] = True
    return {"ok": True}


@app.post("/api/follows/fetch/special")
def fetch_special():
    """Fetch and protect special follows (tagid=-10)."""
    client = get_client()
    uids: list[int] = []
    pn = 1
    while True:
        r = client.get(
            "https://api.bilibili.com/x/relation/tags",
            params={"tagid": -10, "pn": pn, "ps": 50},
        )
        if r.get("code") != 0:
            break
        items = r.get("data", [])
        if not items or not isinstance(items, list):
            break
        for u in items:
            if isinstance(u, dict) and "mid" in u:
                uids.append(u["mid"])
        pn += 1

    conn = database.get_conn()
    for uid in uids:
        conn.execute(
            "INSERT OR REPLACE INTO verdicts (mid, verdict, rule_keep, keep_score) "
            "VALUES (?, 'protected', '特别关注', 999)",
            (uid,),
        )
    conn.commit()
    conn.close()
    return {"count": len(uids)}


# ── Filter ──────────────────────────────────────────────────

@app.post("/api/filter/run")
def filter_run():
    """Run rule engine on all follows, save verdicts."""
    rows = database.get_all_with_verdicts()
    engine = _app_engine
    verdicts = []
    for row in rows:
        user = {
            "uname": row.get("uname", ""),
            "sign": row.get("sign", ""),
            "mtime": row.get("mtime", 0),
        }
        ov = row.get("official_verify_type", 0)
        vip = row.get("vip_status", 0) == 1

        result = engine.evaluate_signature(user, official_verify=ov, is_vip=vip)
        verdicts.append({
            "mid": row["mid"],
            "verdict": "unreviewed",
            "rule_keep": ", ".join(result.matched_keep),
            "rule_delete": ", ".join(result.matched_delete),
            "rule_probe": ", ".join(result.matched_probe),
            "keep_score": result.keep_score,
            "delete_score": result.delete_score,
        })

    database.save_verdicts(verdicts)
    return {"count": len(verdicts)}


@app.post("/api/filter/probe")
def filter_probe():
    """Deep probe undetected accounts."""
    client = get_client()
    global _probe_progress
    _probe_progress = {"current": 0, "total": 0, "running": True}
    _stop_flags["probe"] = False

    rows = database.get_all_with_verdicts()
    # Probe accounts without existing probe data
    uids = [str(row["mid"]) for row in rows if row.get("archive_count") is None]

    if not uids:
        _probe_progress["running"] = False
        return {"count": 0, "skipped": True, "message": "所有账号已探测"}

    _probe_progress["total"] = len(uids)

    def _run():
        try:
            def progress_cb(done, total):
                global _probe_progress
                _probe_progress = {"current": done, "total": total, "running": True}
                if _stop_flags.get("probe"):
                    raise RuntimeError("stopped")

            results = batch_probe(client, uids, concurrency=5, batch_delay=3.0,
                                  progress_callback=progress_cb)
            database.save_probes(results)

            # Run probe rules
            engine = _app_engine
            verdicts = []
            for p in results:
                result = engine.evaluate_probe(p)
                if result.matched_probe or result.matched_keep:
                    verdicts.append({
                        "mid": p["uid"],
                        "rule_probe": ", ".join(result.matched_probe),
                        "rule_keep": ", ".join(result.matched_keep),
                        "keep_score": result.keep_score,
                        "delete_score": result.delete_score,
                    })
            if verdicts:
                database.save_verdicts(verdicts)

            global _probe_progress
            _probe_progress = {"current": len(uids), "total": len(uids), "running": False}
        except RuntimeError:
            _probe_progress["running"] = False
        except Exception as e:
            _probe_progress["running"] = False
            logger.error(f"Probe failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return {"count": len(uids), "running": True}


@app.get("/api/filter/progress")
def filter_progress():
    return _probe_progress


@app.post("/api/filter/probe/stop")
def filter_probe_stop():
    _stop_flags["probe"] = True
    return {"ok": True}


# ── Review ──────────────────────────────────────────────────

@app.get("/api/review/list")
def review_list(
    verdict: str | None = Query(None),
    search: str = Query(""),
    sort_by: str = Query("delete_score"),
    sort_dir: str = Query("desc"),
):
    """Get follows with verdicts, paginated."""
    conn = database.get_conn()
    query = """
        SELECT f.*,
               p.archive_count, p.video_count, p.follower as probe_follower,
               p.following, p.total_view, p.level, p.spacesta, p.ff_ratio,
               v.verdict, v.rule_keep, v.rule_delete, v.rule_probe,
               v.keep_score, v.delete_score, v.note
        FROM follows f
        LEFT JOIN probes p ON f.mid = p.mid
        LEFT JOIN verdicts v ON f.mid = v.mid
        WHERE 1=1
    """
    params: list = []
    if verdict and verdict != "all":
        query += " AND v.verdict = ?"
        params.append(verdict)
    if search:
        query += " AND (f.mid LIKE ? OR f.uname LIKE ? OR f.sign LIKE ?)"
        p = f"%{search}%"
        params.extend([p, p, p])

    # Safe sort
    safe_cols = {"mid", "uname", "delete_score", "keep_score", "follower",
                 "archive_count", "level", "total_view", "ff_ratio", "spacesta"}
    if sort_by not in safe_cols:
        sort_by = "delete_score"
    direction = "DESC" if sort_dir == "desc" else "ASC"
    query += f" ORDER BY {sort_by} {direction}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    items = []
    for row in rows:
        items.append({
            "mid": row["mid"],
            "uname": row["uname"],
            "sign": row["sign"] or "",
            "face": row["face"] or "",
            "mtime": row["mtime"],
            "official": "个人" if row["official_verify_type"] == 0 else
                        ("机构" if row["official_verify_type"] == 1 else
                         (row.get("official_verify_desc", "") or "—")),
            "official_type": row["official_verify_type"],
            "vip": "年度" if row.get("vip_type") == 2 else
                   ("月度" if row.get("vip_status") == 1 else "无"),
            "follower": row.get("probe_follower", -1) or -1,
            "archive_count": row.get("archive_count", -1) or -1,
            "level": row.get("level", -1) or -1,
            "total_view": row.get("total_view", -1) or -1,
            "ff_ratio": row.get("ff_ratio", 0.0) or 0.0,
            "spacesta": row.get("spacesta", 0) or 0,
            "verdict": row.get("verdict", "unreviewed") or "unreviewed",
            "rule_keep": row.get("rule_keep", "") or "",
            "rule_delete": row.get("rule_delete", "") or "",
            "delete_score": row.get("delete_score", 0) or 0,
            "keep_score": row.get("keep_score", 0) or 0,
        })
    return {"items": items, "count": len(items)}


@app.post("/api/review/verdict")
def review_verdict(data: dict):
    """Set single verdict. Body: {mid, verdict}"""
    mid = data.get("mid")
    verdict = data.get("verdict", "unreviewed")
    if not mid:
        raise HTTPException(400, "mid required")
    conn = database.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO verdicts (mid, verdict, reviewed_at) VALUES (?, ?, datetime('now'))",
        (mid, verdict),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/review/verdict/batch")
def review_verdict_batch(data: dict):
    """Batch set verdicts. Body: {mids: [int], verdict: str}"""
    mids = data.get("mids", [])
    verdict = data.get("verdict", "unreviewed")
    if not mids:
        raise HTTPException(400, "mids required")
    conn = database.get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO verdicts (mid, verdict, reviewed_at) VALUES (?, ?, datetime('now'))",
        [(mid, verdict) for mid in mids],
    )
    conn.commit()
    conn.close()
    return {"ok": True, "count": len(mids)}


# ── Unfollow ────────────────────────────────────────────────

@app.get("/api/unfollow/list")
def unfollow_list():
    """Get accounts marked for deletion."""
    rows = database.get_all_with_verdicts(verdict_filter="delete")
    items = [{"mid": row["mid"], "uname": row["uname"]} for row in rows]
    return {"items": items, "count": len(items)}


@app.post("/api/unfollow/execute")
def unfollow_execute():
    """Execute batch unfollow for delete-verdict accounts."""
    client = get_client()
    rows = database.get_all_with_verdicts(verdict_filter="delete")
    uids = [str(row["mid"]) for row in rows]
    if not uids:
        return {"success": 0, "fail": 0, "message": "无待取关账号"}

    _stop_flags["unfollow"] = False

    def progress_cb(done, total, success):
        if _stop_flags.get("unfollow"):
            raise RuntimeError("stopped")

    success, fail = batch_unfollow(client, uids, progress_callback=progress_cb)
    return {"success": success, "fail": fail, "total": len(uids)}


@app.post("/api/unfollow/stop")
def unfollow_stop():
    _stop_flags["unfollow"] = True
    return {"ok": True}


# ── Custom APIs ─────────────────────────────────────────────

@app.get("/api/custom-apis")
def custom_apis_list():
    p = database.get_data_dir() / "custom_apis.toml"
    if not p.exists():
        return {"apis": []}
    try:
        import tomllib
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        return {"apis": data.get("apis", [])}
    except Exception:
        return {"apis": []}


@app.post("/api/custom-apis/save")
def custom_apis_save(data: dict):
    p = database.get_data_dir() / "custom_apis.toml"
    content = "[apis]\n"
    for api in data.get("apis", []):
        content += f"[[apis]]\nname = \"{api['name']}\"\nurl = \"{api['url']}\"\n"
    p.write_text(content, encoding="utf-8")
    return {"ok": True}


@app.get("/api/custom-rules")
def custom_rules_list():
    p = database.get_data_dir() / "custom_rules.toml"
    if not p.exists():
        return {"rules": []}
    try:
        import tomllib
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        return {"rules": data.get("delete_rules", [])}
    except Exception:
        return {"rules": []}


# ── Standalone API server entry ─────────────────────────────

def start_api_server():
    """Start FastAPI server directly (without pywebview)."""
    uvicorn.run(app, host="127.0.0.1", port=9000, log_level="info")


if __name__ == "__main__":
    start_api_server()
