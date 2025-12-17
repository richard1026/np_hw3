# games/gomoku/main.py


import pygame
import sys
import socket
import json
import threading
import struct
import argparse
import time
import os

# --- Helper: Robust Receive ---
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

# --- Game Constants ---
BOARD_SIZE = 15
CELL_SIZE = 40
MARGIN = 40
WINDOW_SIZE = BOARD_SIZE * CELL_SIZE + MARGIN * 2
BG_COLOR = (220, 179, 92)
LINE_COLOR = (0, 0, 0)
BLACK_COLOR = (0, 0, 0)
WHITE_COLOR = (255, 255, 255)

class GomokuClient:
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username
        self.sock = None
        self.running = True
        
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.my_role = "Spectator"  
        self.turn = 'black'  # Black goes first
        self.status = "Connecting..."
        self.winner = None
        
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
            except Exception as e:
                time.sleep(0.5)
        self.status = "Connection Failed"

    def network_loop(self):
        while self.running:
            msg = recv_frame(self.sock)
            if not msg:
                self.status = "Disconnected"
                break
            
            type_ = msg.get("type")
            if type_ == "ping": continue
            
            if type_ == "init":
                self.my_role = msg.get("role")
                # [UI] English Role Description
                role_en = "Black (First)" if self.my_role == "black" else "White (Second)"
                self.status = f"You are: {role_en}. Waiting..."
                
                if self.screen:
                    pygame.display.set_caption(f"Gomoku - {self.username} [{role_en}]")
            
            elif type_ == "gamestart":
                self.status = "Game Start! Black goes first."
            
            elif type_ == "move":
                r, c, color = msg["row"], msg["col"], msg["color"]
                if self.board[r][c] is None:
                    self.board[r][c] = color
                    self.turn = "white" if color == "black" else "black"
                    self.check_win(r, c, color)
                    if not self.winner:
                        self.update_status()
            
            elif type_ == "error":
                self.status = f"Error: {msg.get('msg')}"
                self.running = False

    def update_status(self):
        # Update status text in English
        if self.turn == self.my_role:
            self.status = ">>> Your Turn! <<<"
        else:
            opp_color = "Black" if self.turn == "black" else "White"
            self.status = f"Waiting for {opp_color}..."

    def check_win(self, row, col, color):
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in directions:
            count = 1
            for sign in [1, -1]:
                r, c = row + dr*sign, col + dc*sign
                while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == color:
                    count += 1
                    r += dr*sign; c += dc*sign
            if count >= 5:
                self.winner = color
                winner_en = "Black" if color == "black" else "White"
                self.status = f"Game Over! {winner_en} Wins!"
                return

    def send_move(self, row, col):
        if self.sock:
            send_frame(self.sock, {
                "type": "move", "row": row, "col": col, "color": self.my_role
            })

    def draw(self):
        if not self.screen: return 

        self.screen.fill(BG_COLOR)
        
        # Draw Grid
        for i in range(BOARD_SIZE):
            s = MARGIN + i * CELL_SIZE
            pygame.draw.line(self.screen, LINE_COLOR, (MARGIN, s), (WINDOW_SIZE-MARGIN, s), 1)
            pygame.draw.line(self.screen, LINE_COLOR, (s, MARGIN), (s, WINDOW_SIZE-MARGIN), 1)

        # Draw Pieces
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c]:
                    color = BLACK_COLOR if self.board[r][c] == "black" else WHITE_COLOR
                    x = MARGIN + c * CELL_SIZE
                    y = MARGIN + r * CELL_SIZE
                    pygame.draw.circle(self.screen, color, (x, y), CELL_SIZE//2 - 2)

        # Draw Status Bar
        pygame.draw.rect(self.screen, (240, 240, 240), (0, 0, WINDOW_SIZE, 50))
        
        # Status Text Color
        if self.winner:
            text_color = (255, 0, 0) # Red for Game Over
        elif self.turn == self.my_role:
            text_color = (0, 0, 255) # Blue for Your Turn
        else:
            text_color = (50, 50, 50) # Gray for Waiting

        if self.font:
            text = self.font.render(self.status, True, text_color)
            rect = text.get_rect(center=(WINDOW_SIZE // 2, 25))
            self.screen.blit(text, rect)
        
        pygame.display.flip()

    def run(self):
        self.connect()
        print("[Game] Initializing Pygame Window...")
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
        pygame.display.set_caption(f"Gomoku - {self.username}")
        
        # Use system default font (English is safe)
        self.font = pygame.font.SysFont("Arial", 24)
        
        clock = pygame.time.Clock()
        
        while self.running:
            clock.tick(30)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.winner:
                    # Check turn and game status
                    if self.my_role == self.turn and ("Start" in self.status or "Turn" in self.status):
                        mx, my = pygame.mouse.get_pos()
                        if my < MARGIN: continue
                        
                        c = round((mx - MARGIN) / CELL_SIZE)
                        r = round((my - MARGIN) / CELL_SIZE)
                        
                        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] is None:
                            self.board[r][c] = self.my_role
                            self.send_move(r, c)
                            self.check_win(r, c, self.my_role)
                            self.turn = "white" if self.my_role == "black" else "black"
                            if not self.winner:
                                self.update_status()
            
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
    GomokuClient(args.host, args.port, args.player).run()