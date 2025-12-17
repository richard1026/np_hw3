# player_client/lobby_client.py


import socket
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List
import os
import json

# 設定專案根目錄，確保能 import common
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from common.protocol import send_frame, recv_frame, recv_file
from common.utils import input_int

SERVER_HOST = "140.113.17.11"
SERVER_PORT = 9800

# --- Plugin 定義 ---
AVAILABLE_PLUGINS = {
    "chat": {"name": "Room Chat Plugin", "desc": "在遊戲房間內顯示獨立的群組聊天視窗"}
}

class LobbyClient:
    def __init__(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((SERVER_HOST, SERVER_PORT))
            self.download_root = Path("downloads") 
            self.download_root.mkdir(exist_ok=True)
            print(f"已連線至 {SERVER_HOST}:{SERVER_PORT}")
        except Exception as e:
            print(f"無法連線至 Server: {e}")
            sys.exit(1)

    def send_req(self, action: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if data is None: data = {}
        try:
            send_frame(self.sock, {"action": action, "data": data})
            resp = recv_frame(self.sock)
            return resp or {"status": "error", "error": "server closed connection"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def download_game(self, game_id: str, username: str) -> bool:
        print(f"正在請求下載遊戲 {game_id} ...")
        resp = self.send_req("player_download_req", {"game_id": game_id})
        
        if resp.get("status") != "ok":
            print("下載失敗:", resp.get("error"))
            return False
            
        file_size = resp["file_size"]
        filename = resp.get("filename", "game.py")
        
        user_game_dir = self.download_root / username / game_id
        save_path = user_game_dir / filename
        temp_path = user_game_dir / (filename + ".tmp")
        
        user_game_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"正在接收 {filename} ({file_size} bytes)...")
        try:
            recv_file(self.sock, str(temp_path), file_size)
            # 原子操作：下載成功才改名，避免壞檔
            if save_path.exists():
                os.remove(save_path)
            os.rename(temp_path, save_path)
            print(f"下載完成！位置: {save_path}")
        except Exception as e:
            print("傳輸中斷或失敗:", e)
            if temp_path.exists(): os.remove(temp_path)
            return False

        print("更新版本紀錄...")
        self.send_req("player_download_game_update_db", {"game_id": game_id})
        return True

    def launch_game(self, game_id: str, context: Dict[str, Any]):
        username = context.get("username")
        
        # 1. 取得連線資訊
        game_host = context.get("game_host", "127.0.0.1")
        game_port = context.get("game_port")
        chat_port = context.get("chat_port") 
        
        if not game_port:
            print(f"[ERROR] 啟動失敗：房間資訊中缺少 game_port")
            return

        # 2. 確認遊戲檔案存在
        user_game_dir = self.download_root / username / game_id
        if not user_game_dir.exists():
            print(f"錯誤：在 {user_game_dir} 找不到遊戲檔案，請先下載")
            return

        py_files = list(user_game_dir.glob("*.py"))
        if not py_files:
            print("錯誤：遊戲目錄中沒有 Python 執行檔")
            return
        
        game_script_path = py_files[0]

        # 3. [Plugin] 啟動獨立聊天室 (如果有安裝且 Server 支援)
        if self.is_plugin_installed(username, "chat") and chat_port:
            print(f"[System] 偵測到 Chat Plugin，正在啟動聊天室...")
            
            chat_script = Path("plugins") / "Chat" / "main.py"
            
            if chat_script.exists():
                cmd_chat = [
                    sys.executable, str(chat_script),
                    "--host", str(game_host),
                    "--port", str(chat_port),
                    "--player", str(username)
                ]
                
                try:
                    
                    plugin_flags = 0x08000000 if sys.platform == "win32" else 0
                    
                    subprocess.Popen(cmd_chat, creationflags=plugin_flags, close_fds=True, shell=False)
                except Exception as e:
                    print(f"[Plugin] 聊天室啟動失敗: {e}")
            else:
                print(f"[Plugin] 找不到插件檔案: {chat_script}")

        # 4. 啟動遊戲主程式
        cmd_game = [
            sys.executable, str(game_script_path),
            "--host", str(game_host),
            "--port", str(game_port),
            "--player", str(username)
        ]
        
        print(f"\n[Lobby] 正在啟動遊戲 (Port {game_port})...")
        try:
           
            game_flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            
            subprocess.Popen(cmd_game, creationflags=game_flags, close_fds=True, shell=False) 
            print("[Lobby] 遊戲視窗已開啟。")
        except Exception as e:
            print(f"啟動失敗: {e}")
    # --- Plugin 管理功能 ---
    def get_plugin_file(self, username: str) -> Path:
        return self.download_root / username / "plugins.json"

    def is_plugin_installed(self, username: str, plugin_key: str) -> bool:
        p_file = self.get_plugin_file(username)
        if not p_file.exists(): return False
        try:
            with open(p_file, "r") as f:
                data = json.load(f)
                return plugin_key in data
        except: return False

    def install_plugin(self, username: str, plugin_key: str):
        p_file = self.get_plugin_file(username)
        data = []
        if p_file.exists():
            try:
                with open(p_file, "r") as f: data = json.load(f)
            except: pass
        
        if plugin_key not in data:
            data.append(plugin_key)
            p_file.parent.mkdir(parents=True, exist_ok=True)
            with open(p_file, "w") as f: json.dump(data, f)
            print(f"成功安裝插件: {AVAILABLE_PLUGINS[plugin_key]['name']}")
        else:
            print("該插件已安裝")

    def remove_plugin(self, username: str, plugin_key: str):
        p_file = self.get_plugin_file(username)
        if not p_file.exists(): return
        try:
            with open(p_file, "r") as f: data = json.load(f)
            if plugin_key in data:
                data.remove(plugin_key)
                with open(p_file, "w") as f: json.dump(data, f)
                print(f"已移除插件: {AVAILABLE_PLUGINS[plugin_key]['name']}")
            else:
                print("尚未安裝此插件")
        except: pass

    def close(self):
        self.sock.close()

def show_games(games: List[Dict[str, Any]]) -> None:
    if not games:
        print("目前沒有可遊玩的遊戲")
        return
    print("ID | 名稱 | 版本 | 作者")
    print("-------------------------------------")
    for g in games:
        print(f'{g["id"]} | {g["name"]} | {g["version"]} | {g["owner"]}')

def show_rooms(rooms: List[Dict[str, Any]]) -> None:
    if not rooms:
        print("目前沒有房間")
        return
    print("ID | 遊戲 | Host | 人數")
    print("-------------------------------------")
    for r in rooms:
        curr = len(r["players"])
        max_p = r.get("max_players", 2)
        print(f'{r["id"]} | {r["game_name"]} | {r["host"]} | {curr}/{max_p}')

def plugin_menu(client: LobbyClient, username: str):
    while True:
        print("\n=== Plugin (擴充功能) 管理 ===")
        print(f"目前使用者: {username}")
        print("--------------------------------")
        
        # 1. 取得所有 Plugin 的 Key (轉成 List 以便用 Index 存取)
        plugin_list = list(AVAILABLE_PLUGINS.keys())
        
        print("可用 Plugin 清單:")
        if not plugin_list:
            print("  (暫無可用 Plugin)")
        else:
            for i, key in enumerate(plugin_list):
                info = AVAILABLE_PLUGINS[key]
                installed = client.is_plugin_installed(username, key)
                status = "[已安裝]" if installed else "[未安裝]"
                # 顯示格式: 1. Room Chat Plugin (chat) [已安裝]
                print(f"  {i+1}. {info['name']} ({key}) {status}")
                print(f"     └── {info['desc']}")
        print("--------------------------------")
        
        print("1. 安裝 Plugin")
        print("2. 移除 Plugin")
        print("3. 返回主選單")
        
        choice = input_int("請選擇 (1-3): ", 1, 3)

        if choice == 1: # 安裝
            if not plugin_list:
                print("目前沒有可安裝的 Plugin")
                continue
                
            idx = input_int(f"請輸入要安裝的 Plugin 編號 (1-{len(plugin_list)}): ", 1, len(plugin_list))
            target_key = plugin_list[idx-1] # 取得對應的 key (例如 'chat')
            
            client.install_plugin(username, target_key)

        elif choice == 2: # 移除
            if not plugin_list:
                print("目前沒有可移除的 Plugin")
                continue

            idx = input_int(f"請輸入要移除的 Plugin 編號 (1-{len(plugin_list)}): ", 1, len(plugin_list))
            target_key = plugin_list[idx-1]
            
            client.remove_plugin(username, target_key)

        elif choice == 3: # 返回
            break

# --- 子選單 1: 遊戲商店 (Store) ---
def menu_store(client: LobbyClient, username: str):
    while True:
        print("\n=== [子選單] 遊戲商店 ===")
        print("1. 瀏覽遊戲列表")
        print("2. 檢視遊戲詳細資訊")
        print("3. 下載 / 更新遊戲")
        print("4. 對遊戲評分與留言")
        print("5. 返回主選單")
        choice = input_int("請選擇 (1-5): ", 1, 5)

        if choice == 1: # 瀏覽
            resp = client.send_req("player_list_games")
            if resp.get("status") == "ok":
                show_games(resp.get("result", []))
            else:
                print("錯誤:", resp.get("error"))

        elif choice == 2: # 詳細
            gid = input("輸入遊戲 ID: ").strip()
            resp = client.send_req("player_game_detail", {"game_id": gid})
            if resp.get("status") != "ok":
                print("錯誤:", resp.get("error"))
                continue
            info = resp["result"]
            game = info["game"]
            print("\n--- 遊戲詳細資訊 ---")
            print(f"名稱: {game['name']}")
            print(f"作者: {game['owner']}")
            print(f"版本: {game['version']}")
            print(f"類型: {game.get('game_type', 'GUI')}")
            print(f"支援人數: {game.get('max_players', 2)} 人")
            desc = game.get("description", "")
            print(f"簡介: {desc if desc else '（尚未提供簡介）'}")
            print("\n--- 評分與留言 ---")
            ratings = info.get("ratings", [])
            if not ratings:
                print("尚無評價")
            else:
                avg_score = sum(r["score"] for r in ratings) / len(ratings)
                print(f"平均評分: {avg_score:.1f} / 5.0")
                print("最新評論:")
                for r in ratings[-5:]:
                    print(f"  - {r['player']}: {r['score']}分 | {r.get('comment','')}")
            print("--------------------\n")

        elif choice == 3: # 下載
            # 為了 UX，先列出遊戲
            resp = client.send_req("player_list_games")
            if resp.get("status") == "ok": show_games(resp.get("result", []))
            
            gid = input("請輸入要下載/更新的遊戲 ID: ").strip()
            # 檢查本地狀態
            user_game_dir = client.download_root / username / gid
            is_installed = user_game_dir.exists() and list(user_game_dir.glob("*.py"))
            
            if not is_installed:
                if input("尚未下載，是否下載？(y/N): ").strip().lower() == 'y':
                    client.download_game(gid, username)
            else:
                if input("已安裝，是否更新/重新下載？(y/N): ").strip().lower() == 'y':
                    client.download_game(gid, username)

        elif choice == 4: # 評分
            gid = input("要評分的遊戲 ID: ").strip()
            score = input_int("評分 (1-5): ", 1, 5)
            comment = input("留言 (限 50 字): ").strip()
            resp = client.send_req("player_rate_game", {"game_id": gid, "score": score, "comment": comment})
            if resp.get("status") == "ok":
                print("評分已送出")
            else:
                print(f"評分失敗: {resp.get('error')}")

        elif choice == 5:
            return # 返回上一層

# --- 子選單 2: 多人大廳 (Lobby) ---
def menu_lobby(client: LobbyClient, username: str):
    while True:
        print("\n=== [子選單] 多人大廳 ===")
        print("1. 瀏覽目前房間")
        print("2. 建立新房間")
        print("3. 加入房間")
        print("4. 返回主選單")
        choice = input_int("請選擇 (1-4): ", 1, 4)

        if choice == 1: # 瀏覽房間
            resp = client.send_req("player_list_rooms")
            rooms = resp.get("result", [])
            show_rooms(rooms)

        elif choice == 2: # 建立房間
            resp = client.send_req("player_list_games")
            if resp.get("status") == "ok": show_games(resp.get("result", []))
            
            gid = input("要建立房間的遊戲 ID: ").strip()
            
            resp2 = client.send_req("player_create_room", {"game_id": gid})
            # 自動更新邏輯
            if resp2.get("status") == "error" and resp2.get("error") == "UPDATE_REQUIRED":
                print("\n[系統] 版本過舊，開始強制更新...")
                if client.download_game(gid, username):
                    print("[系統] 更新完成，重試建立...")
                    resp2 = client.send_req("player_create_room", {"game_id": gid})
                else:
                    print("[系統] 更新失敗。")
                    continue

            if resp2.get("status") == "ok":
                room = resp2["result"]
                print(f"房間建立成功 (ID: {room['id']})")
                context = room.copy(); context["username"] = username
                client.launch_game(gid, context)
            else:
                print("錯誤:", resp2.get("error"))

        elif choice == 3: # 加入房間
            resp = client.send_req("player_list_rooms")
            rooms = resp.get("result", [])
            show_rooms(rooms)
            if not rooms: continue

            rid = input("要加入的房間 ID: ").strip()
            resp2 = client.send_req("player_join_room", {"room_id": rid})
            
            # 自動更新邏輯
            if resp2.get("status") == "error" and resp2.get("error") == "UPDATE_REQUIRED":
                required_gid = str(resp2.get("game_id"))
                print(f"\n[系統] 版本過舊，開始強制更新...")
                if client.download_game(required_gid, username):
                    print("[系統] 更新完成，重試加入...")
                    resp2 = client.send_req("player_join_room", {"room_id": rid})
                else:
                    print("[系統] 更新失敗。")
                    continue

            if resp2.get("status") == "ok":
                room = resp2["result"]
                gid = str(room["game_id"])
                print(f"已加入房間，遊戲ID: {gid}")
                context = room.copy(); context["username"] = username
                client.launch_game(gid, context)
            else:
                print("錯誤:", resp2.get("error"))

        elif choice == 4:
            return

# --- 主選單 ---
def player_session_menu(client: LobbyClient, username: str) -> None:
    print(f"\n歡迎回來, 玩家 {username}")
    while True:
        print("\n=== 玩家主選單 ===")
        print("1. 遊戲商店 (瀏覽/下載/評分)")
        print("2. 多人大廳 (建立/加入房間)")
        print("3. Plugin (擴充功能) 管理")
        print("4. 登出")
        
        choice = input_int("請選擇 (1-4): ", 1, 4)

        if choice == 1:
            menu_store(client, username)
        elif choice == 2:
            menu_lobby(client, username)
        elif choice == 3:
            plugin_menu(client, username) # 呼叫先前寫好的 plugin_menu
        else:
            client.send_req("logout")
            return

def main_menu():
    client = LobbyClient()
    try:
        while True:
            print("\n=== Lobby Client ===")
            print("1. 註冊 / 2. 登入 / 3. 離開")
            choice = input_int("選: ", 1, 3)
            if choice == 1:
                u = input("User: "); p = input("Pass: ")
                print(client.send_req("register", {"user_type": "player", "username": u, "password": p}))
            elif choice == 2:
                u = input("User: "); p = input("Pass: ")
                resp = client.send_req("login", {"user_type": "player", "username": u, "password": p})
                if resp.get("status") == "ok":
                    player_session_menu(client, u)
                else:
                    print(resp)
            else:
                break
    finally:
        client.close()

if __name__ == "__main__":
    main_menu()