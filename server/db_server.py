# server/db_server.py
#
# 簡易 Database Server（獨立行程）
# - TCP + JSON + Length-Prefixed Framing
# - 所有資料操作一律走 Socket API
# - 底層用單一 JSON 檔持久化

import json
import os
import socket
import threading
from typing import Any, Dict, List, Optional

# 讓 `from common.protocol import ...` 能找到模組
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from common.protocol import send_frame, recv_frame  # type: ignore

HOST = "0.0.0.0"
PORT = 9900
DB_FILE = ROOT / "db_data.json"
LOCK = threading.Lock()


class SimpleDB:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        # 一開始就確保有 _counters
        self.data: Dict[str, Any] = {"_counters": {}}
        #print(f"[DB] __init__ initial self.data['_counters'] type: {type(self.data['_counters'])}")
        self.load()
        #print(f"[DB] __init__ after load self.data['_counters'] type: {type(self.data['_counters'])}")

    def load(self) -> None:
        # 若檔案存在就讀進來
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                #print(f"[DB] load from file, self.data content: {self.data}")
                #print(f"[DB] load from file, self.data['_counters'] type: {type(self.data['_counters']) if '_counters' in self.data else 'not present'}")
            except Exception as e:
                print(f"[WARN] load DB failed: {e}")
                self.data = {}
                print(f"[DB] load failed, self.data['_counters'] reset. type: {type(self.data['_counters']) if '_counters' in self.data else 'not present'}")

        # ---- 統一在這裡補上必要欄位 ----
        if "_counters" not in self.data or not isinstance(self.data["_counters"], dict):
            print(f"[DB] Fixing _counters. Current type: {type(self.data['_counters']) if '_counters' in self.data else 'not present'}")
            self.data["_counters"] = {}
        print(f"[DB] load finished, final self.data['_counters'] type: {type(self.data['_counters'])}")

        # 這幾個 collection 可能之後會用到：先建好
        for col in ("developers", "players", "games", "player_games", "ratings"):
            self.data.setdefault(col, {})
            # 若還沒有 counter，就用目前筆數當起始值
            self.data["_counters"].setdefault(col, len(self.data[col]))

    def save(self) -> None:
        print(f"[DB] Saving data. self.data['_counters'] type: {type(self.data['_counters'])}")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # collection generic helpers -------------------------

    def _ensure_col(self, col: str) -> Dict[str, Any]:
        if col not in self.data:
            self.data[col] = {}
        return self.data[col]

    def _next_id(self, col: str) -> str:
        print(f"[DB] _next_id called for col: {col}. self.data['_counters'] type: {type(self.data['_counters'])}")
        c = self.data["_counters"].get(col, 0) + 1
        self.data["_counters"][col] = c
        return str(c)

    def create(self, col: str, record: Dict[str, Any]) -> Dict[str, Any]:
        colmap = self._ensure_col(col)
        new_id = self._next_id(col)
        rec = dict(record)
        rec["id"] = new_id
        colmap[new_id] = rec
        self.save()
        return rec

    def read(self, col: str, rec_id: str) -> Optional[Dict[str, Any]]:
        colmap = self._ensure_col(col)
        return colmap.get(rec_id)

    def update(self, col: str, rec_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        colmap = self._ensure_col(col)
        if rec_id not in colmap:
            return None
        colmap[rec_id].update(patch)
        self.save()
        return colmap[rec_id]

    def delete(self, col: str, rec_id: str) -> bool:
        colmap = self._ensure_col(col)
        if rec_id in colmap:
            del colmap[rec_id]
            self.save()
            return True
        return False

    def list_all(self, col: str) -> List[Dict[str, Any]]:
        colmap = self._ensure_col(col)
        return list(colmap.values())

    def query(self, col: str, filt: Dict[str, Any]) -> List[Dict[str, Any]]:
        colmap = self._ensure_col(col)
        res = []
        for rec in colmap.values():
            ok = True
            for k, v in filt.items():
                if rec.get(k) != v:
                    ok = False
                    break
            if ok:
                res.append(rec)
        return res


DB = SimpleDB(DB_FILE)


def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Request:
      {
        "action": "create|read|update|delete|list|query|ping",
        "collection": "developers|players|games|ratings|...",
        ...
      }
    """
    act = req.get("action")
    if act == "ping":
        return {"status": "ok", "result": "pong"}

    col = req.get("collection")
    if not isinstance(col, str):
        return {"status": "error", "error": "collection required"}

    with LOCK:
        try:
            if act == "create":
                rec = DB.create(col, req.get("record") or {})
                return {"status": "ok", "result": rec}
            if act == "read":
                rec_id = str(req.get("id"))
                rec = DB.read(col, rec_id)
                if rec is None:
                    return {"status": "error", "error": "not found"}
                return {"status": "ok", "result": rec}
            if act == "update":
                rec_id = str(req.get("id"))
                patch = req.get("patch") or {}
                rec = DB.update(col, rec_id, patch)
                if rec is None:
                    return {"status": "error", "error": "not found"}
                return {"status": "ok", "result": rec}
            if act == "delete":
                rec_id = str(req.get("id"))
                ok = DB.delete(col, rec_id)
                return {"status": "ok", "result": ok}
            if act == "list":
                res = DB.list_all(col)
                return {"status": "ok", "result": res}
            if act == "query":
                filt = req.get("filter") or {}
                res = DB.query(col, filt)
                return {"status": "ok", "result": res}
            return {"status": "error", "error": f"unknown action {act}"}
        except Exception as e:
            print(f"[ERROR] Exception in handle: type={type(e)}, message='{e}'")
            return {"status": "error", "error": f"exception: {e}"}


def worker(conn: socket.socket, addr) -> None:
    print(f"[DB] new connection from {addr}")
    try:
        while True:
            req = recv_frame(conn)
            if req is None:
                break
            resp = handle(req)
            send_frame(conn, resp)
    finally:
        conn.close()
        print(f"[DB] closed {addr}")


def main() -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(128)
            # [修正] 設定 1 秒逾時
            s.settimeout(1.0)
            
            print(f"[DB] listening on {HOST}:{PORT} (Press Ctrl+C to stop)")
            
            while True:
                try:
                    conn, addr = s.accept()
                    conn.settimeout(None) # 恢復阻塞
                    t = threading.Thread(target=worker, args=(conn, addr), daemon=True)
                    t.start()
                
                except socket.timeout:
                    continue
                    
                except OSError:
                    break
                    
    except KeyboardInterrupt:
        print("\n[DB] Server stopping...")
        # 這裡可以做存檔動作 DB.save()，雖然 worker 操作時就會存，但保險起見
        if 'DB' in globals():
            print("[DB] Saving data before exit...")
            DB.save()
            
    finally:
        print("[DB] Server closed.")


if __name__ == "__main__":
    main()
