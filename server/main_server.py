# server/main_server.py

import socket
import threading
import random
import time
import struct
import json
from typing import Any, Dict, Tuple, Optional, List
import sys
from pathlib import Path

# 設定路徑以便讀取 common 模組
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from common.protocol import send_frame, recv_frame, recv_file, send_file

# --- 設定與全域變數 ---
DB_HOST = "127.0.0.1"
DB_PORT = 9900
HOST = "0.0.0.0"
PORT = 9800

ONLINE: Dict[Tuple[str, str], int] = {}
ROOMS_LOCK = threading.Lock()
ROOMS: Dict[int, Dict[str, Any]] = {}
NEXT_ROOM_ID = 1
STORAGE_DIR = ROOT / "server" / "storage"
GAME_PORT_RANGE = list(range(20000, 20100))

# --- Network Helpers ---
def recv_exact(sock, n):
    data = b''
    try:
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk: return None
            data += chunk
        return data
    except: return None

def robust_recv_frame(sock):
    try:
        header = recv_exact(sock, 4)
        if not header: return None
        (length,) = struct.unpack("!I", header)
        body = recv_exact(sock, length)
        if not body: return None
        return json.loads(body.decode("utf-8"))
    except: return None

def send_ping_unsafe(sock):
    data = json.dumps({"type": "ping"}).encode("utf-8")
    header = struct.pack("!I", len(data))
    sock.sendall(header + data)

# --- DB & Logic Helpers ---
#建立一個短暫連線到 DB Server，送出請求並等待回應
def db_req(req: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with socket.create_connection((DB_HOST, DB_PORT)) as s:
            send_frame(s, req)
            return recv_frame(s) or {"status": "error", "error": "db no response"}
    except Exception as e:
        return {"status": "error", "error": f"db connection failed: {e}"}
#將參與這場遊戲的所有玩家，在資料庫中的 has_played 欄位設為 True
def _record_play_history(game_id: str, players: List[str]):
    for p in players:
        r = db_req({"action": "query", "collection": "player_games", "filter": {"player": p, "game_id": game_id}})
        if r.get("status") == "ok" and r.get("result"):
            rec_id = r["result"][0]["id"]
            db_req({"action": "update", "collection": "player_games", "id": rec_id, "patch": {"has_played": True}})
#去資料庫查找特定的使用者資料
def _find_user(utype, user):
    col = "developers" if utype == "developer" else "players"
    res = db_req({"action": "query", "collection": col, "filter": {"username": user}})
    return res["result"][0] if res.get("result") else None
#確認目前的連線 Session 是否已登入，且身分正確。
def _require_player(s):
    if not s.get("logged_in") or s.get("user_type") != "player":
        return {"status": "error", "error": "Auth required"}

def _require_dev(s):
    if not s.get("logged_in") or s.get("user_type") != "developer":
        return {"status": "error", "error": "Dev Auth required"}
#檢查玩家擁有的遊戲版本，是否等於 Server 上的最新版本
def _check_version(user, gid):
    r1 = db_req({"action": "read", "collection": "games", "id": gid})
    if r1.get("status")!="ok": return False
    r2 = db_req({"action": "query", "collection": "player_games", "filter": {"player": user, "game_id": gid}})
    return r2.get("result") and r2["result"][0]["version"] == r1["result"]["version"]

# --- GameSession Class ---
class GameSession(threading.Thread):
    def __init__(self, room_id: int, game_port: int, players_count: int = 2):
        super().__init__()
        self.room_id = room_id
        self.game_port = game_port
        self.chat_port = game_port + 5000 
        self.expected_players = players_count
        self.game_sockets = []
        self.chat_sockets = [] 
        self.running = True
        self.daemon = True 

    def run(self):
        print(f"[Session {self.room_id}] Game Port: {self.game_port}, Chat Port: {self.chat_port}")
        threading.Thread(target=self.run_chat_server, daemon=True).start()
        self.run_game_server()
#啟動 Plugin 用的聊天 Socket Server。邏輯：等待連線 -> 接受連線 -> 為每個連線開啟 chat_relay 執行緒。
    def run_chat_server(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", self.chat_port))
            srv.listen(10)
            srv.settimeout(1.0)
            while self.running:
                try:
                    conn, _ = srv.accept()
                    self.chat_sockets.append(conn)
                    threading.Thread(target=self.chat_relay, args=(conn,), daemon=True).start()
                except socket.timeout: continue
                except: break
        finally:
            srv.close()
    #聊天室廣播
    def chat_relay(self, conn):
        try:
            while self.running:
                msg = robust_recv_frame(conn)
                if not msg: break
                dead = []
                for s in self.chat_sockets:
                    try:
                        data = json.dumps(msg).encode("utf-8")
                        header = struct.pack("!I", len(data))
                        s.sendall(header + data)
                    except: dead.append(s)
                for d in dead: 
                    if d in self.chat_sockets: self.chat_sockets.remove(d)
        except: pass
        finally:
            if conn in self.chat_sockets: self.chat_sockets.remove(conn)
            try: conn.close()
            except: pass
#階段一 (等待)：等待玩家連線，發送 init 。階段二 (開始)：人滿了 -> 呼叫 _record_play_history (紀錄已遊玩) -> 廣播 gamestart。階段三 (轉發)：進入 game_relay_loop。
    def run_game_server(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", self.game_port))
            srv.listen(self.expected_players)
            srv.settimeout(1.0)
            start_time = time.time() 
            
            while len(self.game_sockets) < self.expected_players and self.running:
                try:
                    conn, addr = srv.accept()
                    conn.settimeout(None) 
                    
                    if self.expected_players == 2:
                        roles = ["black", "white"]
                        role = roles[len(self.game_sockets)]
                    else:
                        role = f"P{len(self.game_sockets) + 1}"

                    self.game_sockets.append(conn)
                    print(f"[Session {self.room_id}] Player {role} joined.")
                    send_frame(conn, {"type": "init", "role": role, "msg": "Waiting..."})
                    time.sleep(0.2)
                except socket.timeout:
                    self.check_game_connections()
                    if not self.game_sockets and time.time() - start_time > 60:
                        self.running = False
                except: pass

            if not self.running: return

            print(f"[Session {self.room_id}] Game Start!")
            with ROOMS_LOCK:
                if self.room_id in ROOMS:
                    players = ROOMS[self.room_id]["players"]
                    game_id = str(ROOMS[self.room_id]["game_id"])
                    threading.Thread(target=_record_play_history, args=(game_id, players)).start()

            time.sleep(2.0)
            self.broadcast_game({"type": "gamestart", "msg": "Game Start!"})
            self.game_relay_loop()

        except Exception as e:
            print(f"[Session {self.room_id}] Game Error: {e}")
        finally:
            self.running = False
            self.broadcast_game({"type": "error", "msg": "Room closed."})
            for s in self.game_sockets: 
                try: s.close() 
                except: pass
            for s in self.chat_sockets:
                try: s.close()
                except: pass
            srv.close()
            with ROOMS_LOCK:
                if self.room_id in ROOMS: del ROOMS[self.room_id]
#在等待階段檢查有沒有人斷線，將死掉的連線移除。
    def check_game_connections(self):
        dead = []
        for s in self.game_sockets:
            try: send_ping_unsafe(s)
            except: dead.append(s)
        for s in dead: self.game_sockets.remove(s)
#收到某玩家的遊戲指令 (移動、下棋)，直接轉發給其他所有玩家。
    def game_relay_loop(self):
        def forward(source, role):
            try:
                while self.running:
                    msg = robust_recv_frame(source)
                    if msg is None: break
                    if msg.get("type") == "ping": continue
                    for other in self.game_sockets:
                        if other != source:
                            try: send_frame(other, msg)
                            except: pass
            except: pass
            finally: self.running = False

        for i, sock in enumerate(self.game_sockets):
            threading.Thread(target=forward, args=(sock, f"P{i}"), daemon=True).start()
        
        while self.running: time.sleep(1)

    def broadcast_game(self, msg):
        for s in self.game_sockets:
            try: send_frame(s, msg)
            except: pass

# --- Handlers ---

def handle_register(conn, session, data): 
    user_type = data.get("user_type")
    username = data.get("username")
    if _find_user(user_type, username):
        return {"status": "error", "error": "帳號已存在"}
    return db_req({"action": "create", "collection": user_type+"s", "record": {"username": username, "password": data["password"]}})

def handle_login(conn, session, data):
    u = _find_user(data["user_type"], data["username"])
    if u and u["password"] == data["password"]:
        key = (data["user_type"], data["username"])
        if key in ONLINE: return {"status": "error", "error": "此帳號已在別處登入"}
        session.update({"logged_in": True, "user_type": data["user_type"], "username": data["username"]})
        ONLINE[key] = 1
        return {"status": "ok"}
    return {"status": "error", "error": "帳號或密碼錯誤"}

def handle_logout(conn, session, data): 
    if session.get("logged_in"): 
        ONLINE.pop((session.get("user_type"), session.get("username")), None)
    session.clear()
    return {"status": "ok"}

# Developer Handlers
def dev_create_game(c, s, d):
    if err := _require_dev(s): return err
    return db_req({"action": "create", "collection": "games", "record": {
        "owner": s["username"], "name": d["name"], "description": d.get("description", ""), 
        "version": d["version"], "max_players": int(d["max_players"]), "game_type": d["game_type"], "deleted": False
    }})

def dev_list_games(c, s, d):
    if err := _require_dev(s): return err
    res = db_req({"action": "query", "collection": "games", "filter": {"owner": s["username"]}})
    return {"status": "ok", "result": [g for g in res.get("result",[]) if not g.get("deleted")]}

def dev_update_game(c, s, d):
    if err := _require_dev(s): return err
    gid = str(d["game_id"])
    r = db_req({"action": "read", "collection": "games", "id": gid})
    if r.get("status") != "ok": return {"status": "error", "error": "遊戲不存在"}
    if r["result"]["owner"] != s["username"]: return {"status": "error", "error": "無權限"}
    patch = {"version": d["version"]}
    if "description" in d: patch["description"] = d["description"]
    return db_req({"action": "update", "collection": "games", "id": gid, "patch": patch})

def dev_delete_game(c, s, d):
    if err := _require_dev(s): return err
    gid = str(d["game_id"])
    r = db_req({"action": "read", "collection": "games", "id": gid})
    if r.get("status") != "ok": return {"status": "error", "error": "遊戲不存在"}
    if r["result"]["owner"] != s["username"]: return {"status": "error", "error": "無權限"}
    return db_req({"action": "update", "collection": "games", "id": gid, "patch": {"deleted": True}})

def handle_upload_init(c, s, d):
    if err := _require_dev(s): return err
    gid = str(d["game_id"])
    
    # 檢查擁有者權限
    r = db_req({"action": "read", "collection": "games", "id": gid})
    if r.get("status") != "ok": return {"status": "error", "error": "遊戲不存在"}
    if r["result"]["owner"] != s["username"]: return {"status": "error", "error": "無權限上傳檔案"}

    path = STORAGE_DIR / gid / d["filename"]
    path.parent.mkdir(parents=True, exist_ok=True)
    
    send_frame(c, {"status": "ready_to_recv"})
    try:
        recv_file(c, str(path), int(d["file_size"]))
        return {"status": "ok", "result": "上傳成功"} 
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Player Handlers
def player_list_games(c, s, d):
    if err := _require_player(s): return err
    res = db_req({"action": "list", "collection": "games"})
    valid_games = [g for g in res.get("result", []) if not g.get("deleted")]
    return {"status": "ok", "result": valid_games}

def player_game_detail(c, s, d):
    if err := _require_player(s): return err
    gid = str(d["game_id"])
    game = db_req({"action": "read", "collection": "games", "id": gid}).get("result")
    if not game or game.get("deleted"): return {"status": "error", "error": "Game not found"}
    ratings = db_req({"action": "query", "collection": "ratings", "filter": {"game_id": gid}}).get("result", [])
    return {"status": "ok", "result": {"game": game, "ratings": ratings}}

def player_download_req(c, s, d):
    if err := _require_player(s): return err
    gid = str(d["game_id"])
    files = list((STORAGE_DIR / gid).glob("*.py"))
    if not files: return {"status": "error", "error": "No file"}
    path = files[0]
    send_frame(c, {"status": "ok", "file_size": path.stat().st_size, "filename": path.name})
    send_file(c, str(path))

def player_download_game_update_db(conn, session, data):
    if err := _require_player(session): return err
    game_id = str(data.get("game_id"))
    r = db_req({"action": "read", "collection": "games", "id": game_id})
    if r.get("status") != "ok": return r
    latest_ver = r["result"].get("version")
    r2 = db_req({"action": "query", "collection": "player_games", "filter": {"player": session["username"], "game_id": game_id}})
    if res := r2.get("result"):
        return db_req({"action": "update", "collection": "player_games", "id": res[0]["id"], "patch": {"version": latest_ver}})
    else:
        return db_req({"action": "create", "collection": "player_games", "record": {
            "player": session["username"], "game_id": game_id, "version": latest_ver, "has_played": False
        }})

def player_rate_game(conn, session, data):
    if err := _require_player(session): return err
    game_id = str(data.get("game_id"))
    score = int(data.get("score"))
    if not (1 <= score <= 5): return {"status": "error", "error": "Score 1-5"}
    r = db_req({"action": "query", "collection": "player_games", "filter": {"player": session["username"], "game_id": game_id}})
    if r.get("status") != "ok" or not r.get("result"): return {"status": "error", "error": "未擁有此遊戲"}
    if not r["result"][0].get("has_played"): return {"status": "error", "error": "您尚未遊玩過此遊戲，無法評分"}
    return db_req({"action": "create", "collection": "ratings", "record": {
        "game_id": game_id, "player": session["username"], "score": score, "comment": data.get("comment", "")
    }})

def player_create_room(conn, session, data):
    global NEXT_ROOM_ID
    if err := _require_player(session): return err
    gid = str(data.get("game_id"))
    if not _check_version(session["username"], gid): return {"status": "error", "error": "UPDATE_REQUIRED"}
    
    r = db_req({"action": "read", "collection": "games", "id": gid})
    game = r["result"]
    if game.get("deleted"): return {"status": "error", "error": "Deleted"}

    with ROOMS_LOCK:
        if len(ROOMS) >= 100: return {"status": "error", "error": "Full"}
        game_port = 0
        for _ in range(50):
            p = random.choice(GAME_PORT_RANGE)
            if not any(r.get("game_port")==p for r in ROOMS.values()):
                game_port = p; break
        if not game_port: return {"status": "error", "error": "No ports"}

        rid = NEXT_ROOM_ID; NEXT_ROOM_ID += 1
        GameSession(rid, game_port, players_count=game.get("max_players", 2)).start()

        ROOMS[rid] = {
            "id": rid, "game_id": gid, "game_name": game["name"],
            "host": session["username"], "players": [session["username"]],
            "max_players": game.get("max_players", 2),
            "game_port": game_port, "game_host": "140.113.17.11", "chat_port": game_port + 5000 
        }
    return {"status": "ok", "result": ROOMS[rid]}

def player_join_room(conn, session, data):
    if err := _require_player(session): return err
    rid = int(data.get("room_id"))
    with ROOMS_LOCK:
        room = ROOMS.get(rid)
        if not room: return {"status": "error", "error": "Not found"}
        if len(room["players"]) >= room.get("max_players", 2): return {"status": "error", "error": "Full"}
        
        gid = str(room["game_id"])
        if not _check_version(session["username"], gid): return {"status": "error", "error": "UPDATE_REQUIRED", "game_id": gid}
        
        if session["username"] not in room["players"]: room["players"].append(session["username"])
        return {"status": "ok", "result": room}

def player_list_rooms(c, s, d): 
    if err := _require_player(s): return err
    return {"status": "ok", "result": list(ROOMS.values())}

# --- Mapping ---
HANDLERS = {
    "register": handle_register, "login": handle_login, "logout": handle_logout,
    "dev_list_games": dev_list_games, "dev_create_game": dev_create_game, 
    "dev_update_game": dev_update_game, "dev_delete_game": dev_delete_game, 
    "dev_upload_init": handle_upload_init,
    "player_list_games": player_list_games, "player_create_room": player_create_room, 
    "player_join_room": player_join_room, "player_list_rooms": player_list_rooms, 
    "player_download_req": player_download_req, 
    "player_download_game_update_db": player_download_game_update_db, 
    "player_game_detail": player_game_detail, 
    "player_rate_game": player_rate_game
}

def client_worker(conn, addr):
    session = {} 
    print(f"[MAIN] New connection from {addr}")
    try:
        while True:
            req = recv_frame(conn)
            if not req: break
            action = req.get("action")
            handler = HANDLERS.get(action)
            if handler:
                resp = handler(conn, session, req.get("data") or {})
                if resp is not None: send_frame(conn, resp)
            else:
                send_frame(conn, {"status": "error", "error": f"Unknown action: {action}"})
    except Exception as e:
        print(f"[MAIN] Error: {e}")
    finally:
        if session.get("logged_in"): 
            ONLINE.pop((session.get("user_type"), session.get("username")), None)
        conn.close()

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT)); s.listen(10)
    s.settimeout(1.0)
    print(f"[MAIN] Listening on {HOST}:{PORT}")
    while True:
        try:
            conn, addr = s.accept()
            conn.settimeout(None)
            threading.Thread(target=client_worker, args=(conn, addr), daemon=True).start()
        except socket.timeout: continue
        except OSError: break

if __name__ == "__main__": main()