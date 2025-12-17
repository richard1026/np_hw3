# plugins/Chat/main.py
# 獨立聊天室視窗 (Tkinter)

import socket
import threading
import struct
import json
import argparse
import sys
import tkinter as tk
from tkinter import scrolledtext
import os

def send_frame(sock, obj):
    try:
        data = json.dumps(obj).encode("utf-8")
        header = struct.pack("!I", len(data))
        sock.sendall(header + data)
    except: pass

def recv_frame(sock):
    try:
        header = sock.recv(4)
        if len(header) < 4: return None
        (length,) = struct.unpack("!I", header)
        body = sock.recv(length)
        if len(body) < length: return None
        return json.loads(body.decode("utf-8"))
    except: return None

class ChatClient:
    def __init__(self, host, port, username):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((host, port))
        except:
            sys.exit(0) # 連不上直接關
            
        self.username = username
        
        # GUI
        self.root = tk.Tk()
        self.root.title(f"Chat - {username}")
        self.root.geometry("300x400")
        
        self.text_area = scrolledtext.ScrolledText(self.root, state='disabled')
        self.text_area.pack(expand=True, fill='both')
        
        self.entry = tk.Entry(self.root)
        self.entry.pack(fill='x', padx=5, pady=5)
        self.entry.bind("<Return>", self.send_msg)
        
        # 啟動接收執行緒
        threading.Thread(target=self.recv_loop, daemon=True).start()
        
        self.root.mainloop()

    def send_msg(self, event):
        msg = self.entry.get()
        if msg:
            payload = {"sender": self.username, "msg": msg}
            send_frame(self.sock, payload)
            self.entry.delete(0, tk.END)

    def recv_loop(self):
        while True:
            data = recv_frame(self.sock)
            if not data: 
                break # Server 斷線 -> 跳出迴圈
            
            sender = data.get("sender", "Unknown")
            msg = data.get("msg", "")
            
            self.text_area.config(state='normal')
            self.text_area.insert(tk.END, f"[{sender}]: {msg}\n")
            self.text_area.see(tk.END)
            self.text_area.config(state='disabled')
        
        # 斷線後，強制殺死整個 Process，關閉視窗
        os._exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--player", required=True)
    args = parser.parse_args()
    
    ChatClient(args.host, args.port, args.player)