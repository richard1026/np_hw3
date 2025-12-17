# games/tictactoe/main.py
# 井字遊戲 (CLI) - Level A


import socket
import json
import threading
import struct
import argparse
import sys
import time

# ==========================================
#      網路底層 Helper
# ==========================================
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
    try:
        data = json.dumps(obj).encode("utf-8")
        header = struct.pack("!I", len(data))
        sock.sendall(header + data)
    except: pass

# ==========================================
#      遊戲邏輯 (CLI)
# ==========================================
class TicTacToe:
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username
        self.sock = None
        self.running = True
        
        # 遊戲狀態
        self.board = [" "] * 9
        self.my_role = "Spectator"
        self.turn = "black" # black 先手 (代表 X)
        self.symbol = "?"   # 自己是 X 還是 O
        self.game_started = False

    def connect(self):
        print(f"正在連線至 {self.host}:{self.port}...")
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            # 啟動接收執行緒
            threading.Thread(target=self.network_loop, daemon=True).start()
        except Exception as e:
            print(f"連線失敗: {e}")
            input("按 Enter 離開...") # 連線失敗也停住
            sys.exit(1)

    def print_board(self):
        """畫出棋盤"""
        b = self.board
        print(f"\n {b[0]} | {b[1]} | {b[2]} ")
        print("---+---+---")
        print(f" {b[3]} | {b[4]} | {b[5]} ")
        print("---+---+---")
        print(f" {b[6]} | {b[7]} | {b[8]} \n")

    def check_win(self):
        """檢查勝負"""
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for x,y,z in wins:
            if self.board[x] == self.board[y] == self.board[z] and self.board[x] != " ":
                return self.board[x]
        if " " not in self.board: return "DRAW"
        return None

    def handle_game_over(self, winner):
        """統一處理遊戲結束顯示"""
        if winner == "DRAW":
            print(f"\n[結束] 遊戲結束！結果: 平局 (Draw)")
        else:
            print(f"\n[結束] 遊戲結束！贏家: {winner}")
        self.running = False

    def network_loop(self):
        """接收 Server 訊息"""
        while self.running:
            msg = recv_frame(self.sock)
            if not msg:
                print("\n[系統] 與伺服器斷線")
                self.running = False
                break
            
            type_ = msg.get("type")
            if type_ == "ping": continue

            if type_ == "init":
                self.my_role = msg.get("role")
                # black 是 X (先手), white 是 O (後手)
                self.symbol = "X" if self.my_role == "black" else "O"
                print(f"\n[系統] 你的角色: {self.my_role} (符號: {self.symbol})")
                print("[系統] 等待對手加入...")

            elif type_ == "gamestart":
                self.game_started = True
                print("\n[系統] 遊戲開始！黑棋 (X) 先攻")
                self.print_board()
                if self.my_role == "black":
                    print(">>> 輪到你了！請輸入位置 (0-8): ", end="", flush=True)

            elif type_ == "move":
                # 收到對手下棋
                idx = msg["index"]
                symbol = msg["symbol"]
                self.board[idx] = symbol
                self.print_board()
                
                winner = self.check_win()
                if winner:
                    self.handle_game_over(winner)
                else:
                    # 切換回合
                    self.turn = "white" if self.turn == "black" else "black"
                    if self.turn == self.my_role:
                        print(">>> 輪到你了！請輸入位置 (0-8): ", end="", flush=True)
                    else:
                        print("等待對手下棋...", flush=True)

    def run(self):
        self.connect()
        # 主迴圈處理輸入
        while self.running:
            # 只有輪到自己且遊戲開始時才讀取輸入
            if self.game_started and self.turn == self.my_role:
                try:
                    move = input()
                    if not self.running: break # 若中途斷線
                    if not move.isdigit(): 
                        print("請輸入數字 (0-8): ", end="", flush=True)
                        continue
                    
                    idx = int(move)
                    if 0 <= idx <= 8 and self.board[idx] == " ":
                        # 1. 更新自己畫面
                        self.board[idx] = self.symbol
                        self.print_board()
                        # 2. 發送給對手
                        send_frame(self.sock, {"type": "move", "index": idx, "symbol": self.symbol})
                        
                        # 3. 檢查勝負
                        winner = self.check_win()
                        if winner:
                            self.handle_game_over(winner)
                        else:
                            self.turn = "white" if self.turn == "black" else "black"
                            print("等待對手下棋...")
                    else:
                        print("無效的位置，請重試: ", end="", flush=True)
                except:
                    break
            else:
                # 沒輪到自己就休息一下，避免 CPU 飆高
                time.sleep(0.1)
        
        #  遊戲迴圈結束後，不要馬上關閉視窗
        if self.sock: self.sock.close()
        print("\n-------------------------")
        input("遊戲已結束，請按 Enter 鍵離開視窗...") 
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="140.113.17.11")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--player", default="Guest")
    parser.add_argument("--room", help="Room ID") 
    args = parser.parse_args()
    TicTacToe(args.host, args.port, args.player).run()