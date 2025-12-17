# developer_client/developer_client.py

import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from common.protocol import send_frame, recv_frame, send_file
from common.utils import input_int  

SERVER_HOST = "140.113.17.11"
SERVER_PORT = 9800

# ==========================================
#      內建遊戲範本 (Template Content)
# ==========================================
GAME_TEMPLATE_CONTENT = r'''
import pygame
import sys
import socket
import json
import threading
import struct
import argparse
import time
import os

# --- Helper: 強健接收 ---
def recv_exact(sock, n):
    data = b''
    try:
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk: return None
            data += chunk
        return data
    except:
        return None

def recv_frame(sock):
    try:
        header = recv_exact(sock, 4)
        if not header: return None
        (length,) = struct.unpack("!I", header)
        body = recv_exact(sock, length)
        if not body: return None
        return json.loads(body.decode("utf-8"))
    except:
        return None

def send_frame(sock, obj):
    try:
        data = json.dumps(obj).encode("utf-8")
        header = struct.pack("!I", len(data))
        sock.sendall(header + data)
    except Exception as e:
        print(f"[Net] Send Error: {e}")

# --- 遊戲參數 ---
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
BG_COLOR = (50, 50, 50)
TEXT_COLOR = (255, 255, 255)

class GameClient:
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username
        self.sock = None
        self.running = True
        
        self.my_role = "Spectator"
        self.status = "Connecting..."

        # [TODO] 在這裡加入你的變數
        
        self.screen = None
        self.font = None

    def connect(self):
        print(f"[Game] Connecting to {self.host}:{self.port}...")
        retry_count = 10
        for i in range(retry_count):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
                print("[Game] Connected! Starting receiver thread...")
                t = threading.Thread(target=self.network_loop, daemon=True)
                t.start()
                return
            except ConnectionRefusedError:
                print(f"[Game] Retry ({i+1}/{retry_count})...")
                time.sleep(0.5)
            except Exception as e:
                self.status = f"Error: {e}"
                return
        self.status = "Connect Failed"

    def network_loop(self):
        print("[Net] Receiver started.")
        while self.running:
            msg = recv_frame(self.sock)
            if not msg:
                self.status = "Disconnected"
                break
            
            type_ = msg.get("type")
            if type_ == "ping": continue
            
            print(f"[Net] Recv: {msg}") 
            sys.stdout.flush()
            
            if type_ == "init":
                self.my_role = msg.get("role")
                self.status = f"Role: {self.my_role}. Waiting..."
                if self.screen:
                    pygame.display.set_caption(f"Game - {self.username} ({self.my_role})")
            
            elif type_ == "gamestart":
                self.status = "Game Started!"
            
            elif type_ == "error":
                self.status = f"Error: {msg.get('msg')}"
                self.running = False

    def draw(self):
        if not self.screen: return 
        self.screen.fill(BG_COLOR)
        # [TODO] 畫出你的玩家
        # pygame.draw.circle(self.screen, (255, 0, 0), (self.player_x, self.player_y), 20)
        if self.font:
            text = self.font.render(self.status, True, TEXT_COLOR)
            self.screen.blit(text, (10, 10))
        pygame.display.flip()

    def run(self):
        self.connect()
        print("[Game] Init Window...")
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(f"Game - {self.username}")
        self.font = pygame.font.SysFont("Arial", 24)
        
        clock = pygame.time.Clock()
        while self.running:
            clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                # [TODO] 加入按鍵偵測
            self.draw()
        
        if self.sock: self.sock.close()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="140.113.17.11")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--player", default="Guest")
    parser.add_argument("--room", help="Room ID") 
    args = parser.parse_args()
    GameClient(args.host, args.port, args.player).run()
'''

def generate_template():
    """在 games/ 下建立新的遊戲專案"""
    print("\n--- 建立新遊戲專案範本 ---")
    project_name = input("請輸入專案資料夾名稱 (例如 my_rpg): ").strip()
    if not project_name:
        print("名稱不可為空")
        return

    # 確保 games 資料夾存在
    base_path = Path(__file__).parent / "games" / project_name
    # 處理路徑相容性 (如果直接在 developer_client 內執行)
    if not base_path.parent.exists():
         base_path = Path("games") / project_name

    try:
        base_path.mkdir(parents=True, exist_ok=True)
        
        # 寫入 main.py
        file_path = base_path / "main.py"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(GAME_TEMPLATE_CONTENT.strip())
            
        print(f"\n[成功] 專案已建立於: {base_path}")
        print(f"主程式路徑: {file_path}")
        print("您可以直接修改該檔案進行開發，完成後使用選項 [2] 上架。")
        
    except Exception as e:
        print(f"[失敗] 無法建立專案: {e}")

# ==========================================
#      Developer Client Logic
# ==========================================

class DevClient:
    def __init__(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((SERVER_HOST, SERVER_PORT))
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

    def upload_game(self, game_id: str):
        print("\n--- 開始上傳遊戲檔案 ---")
        filepath = input("請輸入遊戲檔案路徑 (例如 games/my_rpg/main.py): ").strip()
        path_obj = Path(filepath)
        if not path_obj.exists():
            print("錯誤: 檔案不存在，請檢查路徑")
            return

        file_size = path_obj.stat().st_size
        filename = path_obj.name

        print(f"準備上傳 {filename} ({file_size} bytes)...")
        
        # 1. Send Init
        resp = self.send_req("dev_upload_init", {
            "game_id": game_id, 
            "file_size": file_size, 
            "filename": filename
        })
        
        if resp.get("status") != "ready_to_recv":
            print("Server 拒絕上傳:", resp.get("error"))
            return
            
        # 2. Send File
        print("正在傳輸檔案...")
        try:
            send_file(self.sock, str(path_obj))
        except Exception as e:
            print(f"傳輸失敗: {e}")
            return
        
        # 3. Recv Final Result
        final_resp = recv_frame(self.sock)
        print("上傳結果:", final_resp.get("result") or final_resp.get("error"))
        
    def close(self):
        self.sock.close()


def show_games(games: List[Dict[str, Any]]) -> None:
    if not games:
        print("目前沒有遊戲")
        return
    print("ID | 名稱 | 版本 | 描述")
    print("-------------------------------------")
    for g in games:
        print(f'{g["id"]} | {g["name"]} | {g["version"]} | {g.get("description","")}')


# --- 子選單: 遊戲管理 ---
def menu_manage_games(client: DevClient):
    while True:
        print("\n=== [子選單] 管理遊戲 ===")
        print("1. 上架新遊戲 (Metadata + File)")
        print("2. 更新遊戲版本 (Metadata + File)")
        print("3. 下架遊戲")
        print("4. 返回主選單")
        choice = input_int("請選擇 (1-4): ", 1, 4)

        if choice == 1: # 上架
            name = input("遊戲名稱: ").strip()
            desc = input("遊戲簡介: ").strip()
            ver = input("初始版本(預設 1.0.0): ").strip() or "1.0.0"
            g_type = input("遊戲類型 (GUI/CLI, 預設 GUI): ").strip().upper() or "GUI"
            max_p = input_int("支援人數 (預設 2): ", 1, 10)

            resp = client.send_req("dev_create_game", {
                "name": name, "description": desc, "version": ver,
                "game_type": g_type, "max_players": max_p,
            })
            
            if resp.get("status") == "ok":
                record = resp.get("result")
                # 兼容性處理
                if isinstance(record, dict) and "id" in record:
                    new_id = str(record["id"])
                    print(f"上架成功 (ID: {new_id})，接下來請上傳檔案...")
                    client.upload_game(new_id)
                else:
                    print("上架成功，但無法自動取得 ID。")
            else:
                print("錯誤:", resp.get("error"))

        elif choice == 2: # 更新
            # 先列出方便看 ID
            resp = client.send_req("dev_list_games")
            if resp.get("status") == "ok": show_games(resp.get("result", []))
            
            gid = input("要更新的遊戲 ID: ").strip()
            ver = input("新版本號: ").strip()
            desc = input("更新遊戲簡介 (按 Enter 跳過不修): ").strip()
            
            payload = {"game_id": gid, "version": ver}
            if desc: payload["description"] = desc
            
            resp2 = client.send_req("dev_update_game", payload)
            if resp2.get("status") == "ok":
                print("版本資訊更新成功，接下來請上傳新檔案...")
                client.upload_game(gid)
            else:
                print("錯誤:", resp2.get("error"))

        elif choice == 3: # 下架
            gid = input("要下架的遊戲 ID: ").strip()
            print(f"\n[警告] 您即將下架遊戲 (ID: {gid})")
            if input("確定要執行下架嗎？(y/N): ").strip().lower() == 'y':
                resp2 = client.send_req("dev_delete_game", {"game_id": gid})
                if resp2.get("status") == "ok":
                    print("已標記為下架:", resp2["result"])
                else:
                    print("錯誤:", resp2.get("error"))
            else:
                print("已取消")

        elif choice == 4:
            return

# --- 主選單  ---
def dev_session_menu(client: DevClient, username: str) -> None:
    print(f"\n歡迎回來, 開發者 {username}")
    while True:
        print("\n=== 開發者功能選單 ===")
        print("1. 查看我的遊戲列表")
        print("2. 管理遊戲 (上架/更新/下架)")
        print("3. 建立遊戲專案範本 (Local)")
        print("4. 登出")
        choice = input_int("請選擇 (1-4): ", 1, 4)

        if choice == 1:
            resp = client.send_req("dev_list_games")
            if resp.get("status") == "ok":
                show_games(resp.get("result", []))
            else:
                print("錯誤:", resp.get("error"))

        elif choice == 2:
            menu_manage_games(client)

        elif choice == 3:
            generate_template()

        else:
            client.send_req("logout")
            print("已登出")
            return


def main_menu() -> None:
    client = DevClient()
    try:
        while True:
            print("\n=== Developer Client 主選單 ===")
            print("1. 註冊開發者帳號")
            print("2. 登入開發者帳號")
            print("3. 離開")
            choice = input_int("請選擇 (1-3): ", 1, 3)

            if choice == 1:
                username = input("帳號: ").strip()
                password = input("密碼: ").strip()
                resp = client.send_req("register", {
                    "user_type": "developer",
                    "username": username,
                    "password": password,
                })
                print("結果:", resp.get("result") or resp.get("error"))
                
            elif choice == 2:
                username = input("帳號: ").strip()
                password = input("密碼: ").strip()
                resp = client.send_req("login", {
                    "user_type": "developer",
                    "username": username,
                    "password": password,
                })
                if resp.get("status") == "ok":
                    dev_session_menu(client, username)
                else:
                    print("登入失敗:", resp.get("error"))
                    
            else:
                print("再見")
                break
    except KeyboardInterrupt:
        print("\n強制結束")
    finally:
        client.close()

if __name__ == "__main__":
    main_menu()