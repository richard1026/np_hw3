# games/chase_gui/main.py
# 多人鬼抓人遊戲 (Tag) - Level C
# 規則：P1 是鬼，P2/P3 是人。
# 鬼贏：30秒內抓完所有人 (存活歸 0)
# 人贏：撐過 30秒 (存活 > 0)

import pygame
import sys
import socket
import json
import threading
import struct
import argparse
import time
import random
import queue

# --- 網路底層 ---
SOCK_LOCK = threading.Lock()

def recv_exact(sock, n):
    data = b''
    try:
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk: return None
            data += chunk
        return data
    except: return None

def recv_frame(sock):
    try:
        header = recv_exact(sock, 4)
        if not header: return None
        (length,) = struct.unpack("!I", header)
        body = recv_exact(sock, length)
        if not body: return None
        return json.loads(body.decode("utf-8"))
    except: return None

def send_frame(sock, obj):
    with SOCK_LOCK:
        try:
            data = json.dumps(obj).encode("utf-8")
            header = struct.pack("!I", len(data))
            sock.sendall(header + data)
        except Exception as e:
            print(f"[Net] Send Error: {e}")

# --- 遊戲設定 ---
WIDTH, HEIGHT = 600, 400
BG_COLOR = (30, 30, 30)
RADIUS = 20

# 顏色定義
COLOR_CHASER = (255, 50, 50)   # 紅色 (鬼)
COLOR_RUNNER = (50, 255, 50)   # 綠色 (人)
COLOR_DEAD   = (100, 100, 100) # 灰色 (死)
COLOR_SELF   = (255, 255, 0)   # 黃色 (自己邊框)

class ChaseGame:
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username
        self.sock = None
        self.running = True
        
        self.msg_queue = queue.Queue()
        
        self.my_role = None
        self.status = "Connecting..."
        self.am_i_alive = True
        
        # 初始位置
        self.x = random.randint(50, WIDTH-50)
        self.y = random.randint(50, HEIGHT-50)
        self.players = {} 
        
        # 計時與勝負
        self.game_started = False
        self.start_time = 0
        self.game_duration = 30 # 30秒
        self.game_over = False
        self.winner_text = ""

        self.screen = None
        self.font = None
        self.big_font = None

    def connect(self):
        print(f"[Game] Connecting to {self.host}:{self.port}...")
        for i in range(10):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
                threading.Thread(target=self.network_loop, daemon=True).start()
                return
            except:
                time.sleep(0.5)
        self.status = "Connect Failed"

    def network_loop(self):
        while self.running:
            msg = recv_frame(self.sock)
            if not msg:
                self.msg_queue.put({"type": "system", "msg": "Disconnected"})
                break
            self.msg_queue.put(msg)

    def process_queue(self):
        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
            except queue.Empty:
                break
            
            type_ = msg.get("type")
            if type_ == "ping": continue

            if type_ == "init":
                self.my_role = msg.get("role")
                if self.my_role == "P1":
                    self.status = "You are CHASER (Red). Waiting..."
                else:
                    self.status = f"You are RUNNER {self.my_role} (Green). Waiting..."
                
                if self.screen:
                    pygame.display.set_caption(f"Chase - {self.username} ({self.my_role})")

            elif type_ == "gamestart":
                self.status = "GAME START! SURVIVE 30s!" if self.my_role != "P1" else "GAME START! CATCH THEM ALL!"
                self.game_started = True
                self.start_time = time.time()
                self.send_pos() 

            elif type_ == "update":
                role = msg["role"]
                if role != self.my_role:
                    if role not in self.players:
                        # 新發現玩家，預設活著
                        self.players[role] = {"x": 0, "y": 0, "alive": True}
                    self.players[role]["x"] = msg["x"]
                    self.players[role]["y"] = msg["y"]
            
            elif type_ == "kill":
                victim = msg["target"]
                if victim == self.my_role:
                    self.am_i_alive = False
                    self.status = "YOU DIED!"
                elif victim in self.players:
                    self.players[victim]["alive"] = False
            
            elif type_ == "system":
                self.status = "Disconnected"
                self.running = False

    def send_pos(self):
        if self.sock and self.my_role and self.am_i_alive and not self.game_over:
            send_frame(self.sock, {
                "type": "update", 
                "role": self.my_role,
                "x": self.x, 
                "y": self.y
            })

    def send_kill(self, target_role):
        if self.sock:
            send_frame(self.sock, {"type": "kill", "target": target_role})

    def get_alive_runners(self):
        """計算目前存活的跑者數量 (扣除 P1 鬼)"""
        count = 0
        # 1. 檢查自己
        if self.my_role != "P1" and self.am_i_alive:
            count += 1
        # 2. 檢查別人
        for role, p in self.players.items():
            if role != "P1" and p.get("alive", True):
                count += 1
        return count

    def check_win_condition(self):
        """檢查遊戲是否結束"""
        if not self.game_started or self.game_over:
            return

        alive_runners = self.get_alive_runners()
        elapsed = time.time() - self.start_time
        remaining = max(0, self.game_duration - elapsed)

        # 條件 1: 鬼贏 (存活跑者 = 0)
        if alive_runners == 0:
            self.game_over = True
            self.winner_text = "CHASER WINS!"
            self.status = "All Runners Caught!"

        # 條件 2: 人贏 (時間到且還有人活著)
        elif remaining == 0:
            self.game_over = True
            self.winner_text = "RUNNERS WIN!"
            self.status = "Time Up! Survivors Win!"

    def check_collisions(self):
        """鬼 (P1) 負責偵測碰撞"""
        if self.my_role != "P1" or not self.am_i_alive or self.game_over:
            return

        my_rect = pygame.Rect(self.x - RADIUS, self.y - RADIUS, RADIUS*2, RADIUS*2)
        
        for role, p in self.players.items():
            # 只抓活著的跑者 (P1 自己不用抓)
            if role != "P1" and p.get("alive", True):
                other_rect = pygame.Rect(p["x"] - RADIUS, p["y"] - RADIUS, RADIUS*2, RADIUS*2)
                if my_rect.colliderect(other_rect):
                    self.send_kill(role)
                    p["alive"] = False 

    def draw(self):
        if not self.screen: return
        self.screen.fill(BG_COLOR)
        
        # 1. 畫別人
        for role, p in self.players.items():
            if not p.get("alive", True): c = COLOR_DEAD
            elif role == "P1": c = COLOR_CHASER
            else: c = COLOR_RUNNER
            
            pygame.draw.circle(self.screen, c, (p["x"], p["y"]), RADIUS)
            
            if self.font and p.get("alive", True):
                lbl = self.font.render(role, True, (255, 255, 255))
                self.screen.blit(lbl, (p["x"]-10, p["y"]-40))

        # 2. 畫自己
        if self.my_role:
            if not self.am_i_alive: my_c = COLOR_DEAD
            elif self.my_role == "P1": my_c = COLOR_CHASER
            else: my_c = COLOR_RUNNER
            
            pygame.draw.circle(self.screen, my_c, (self.x, self.y), RADIUS)
            pygame.draw.circle(self.screen, COLOR_SELF, (self.x, self.y), RADIUS+2, 2)

        # 3. UI 資訊 (狀態 + 計時 + 存活數)
        if self.font:
            # 狀態列
            status_surf = self.font.render(self.status, True, (255, 255, 255))
            self.screen.blit(status_surf, (10, 10))
            
            if self.game_started:
                # 倒數計時
                elapsed = time.time() - self.start_time
                remain = max(0, self.game_duration - elapsed)
                timer_color = (255, 50, 50) if remain < 10 else (255, 255, 255)
                timer_surf = self.font.render(f"Time: {remain:.1f}s", True, timer_color)
                self.screen.blit(timer_surf, (WIDTH - 150, 10))
                
                # 存活人數
                alive = self.get_alive_runners()
                alive_surf = self.font.render(f"Runners Alive: {alive}", True, (50, 255, 50))
                self.screen.blit(alive_surf, (10, 40))

        # 4. 遊戲結束大字
        if self.game_over and self.big_font:
            over_surf = self.big_font.render(self.winner_text, True, (255, 215, 0)) # 金色
            rect = over_surf.get_rect(center=(WIDTH//2, HEIGHT//2))
            
            # 畫個半透明黑底
            bg_rect = pygame.Surface((WIDTH, 100))
            bg_rect.set_alpha(128)
            bg_rect.fill((0,0,0))
            self.screen.blit(bg_rect, (0, HEIGHT//2 - 50))
            self.screen.blit(over_surf, rect)

        pygame.display.flip()

    def run(self):
        self.connect()
        print("[Game] Init Window...")
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(f"Chase - {self.username}")
        self.font = pygame.font.SysFont("Arial", 24)
        self.big_font = pygame.font.SysFont("Arial", 64, bold=True)
        
        clock = pygame.time.Clock()
        last_sync = time.time()
        
        while self.running:
            clock.tick(60)
            
            # 1. 處理網路
            self.process_queue()
            
            # 2. 檢查勝負
            self.check_win_condition()

            # 3. 輸入與移動 (活著且遊戲進行中)
            moved = False
            if self.am_i_alive and not self.game_over:
                keys = pygame.key.get_pressed()
                speed = 5
                if self.my_role == "P1": speed = 6 # 鬼跑快一點
                
                if keys[pygame.K_LEFT]:  self.x -= speed; moved = True
                if keys[pygame.K_RIGHT]: self.x += speed; moved = True
                if keys[pygame.K_UP]:    self.y -= speed; moved = True
                if keys[pygame.K_DOWN]:  self.y += speed; moved = True
                
                self.x = max(RADIUS, min(WIDTH-RADIUS, self.x))
                self.y = max(RADIUS, min(HEIGHT-RADIUS, self.y))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
            
            if self.am_i_alive and not self.game_over and (moved or (time.time() - last_sync > 0.1)):
                self.send_pos()
                last_sync = time.time()

            # 4. 碰撞 (只有鬼)
            self.check_collisions()

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
    ChaseGame(args.host, args.port, args.player).run()