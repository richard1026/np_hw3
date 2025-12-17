# common/protocol.py
# Length-Prefixed Framing Protocol (4-byte big-endian) + JSON
# Robust Version: 解決 TCP 黏包與斷包問題

import json
import struct
import socket
import os
from typing import Any, Dict, Optional

HEADER_SIZE = 4  # 4 bytes length header

def send_frame(sock: socket.socket, obj: Dict[str, Any]) -> None:
    """
    將 Python dict -> JSON bytes，
    前面加 4 bytes big-endian 長度後送出。
    """
    try:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        header = struct.pack("!I", len(data))
        sock.sendall(header + data)
    except Exception as e:
        # print(f"[Protocol] Send error: {e}")
        pass

def recv_exact(sock: socket.socket, size: int) -> Optional[bytes]:
    """
    從 socket 確保讀取剛好 size bytes。
    如果中途斷線或讀不到，回傳 None。
    """
    buf = b""
    try:
        while len(buf) < size:
            chunk = sock.recv(size - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf
    except:
        return None

def recv_frame(sock: socket.socket) -> Optional[Dict[str, Any]]:
    """
    收一個完整 frame (Robust Version)：
      1. 使用 recv_exact 讀取 4 bytes header
      2. 解析長度
      3. 使用 recv_exact 讀取 body
    """
    try:
        # 1. 讀取 Header
        header = recv_exact(sock, HEADER_SIZE)
        if header is None:
            return None
            
        (length,) = struct.unpack("!I", header)
        if length == 0:
            return {}
            
        # 2. 讀取 Body
        body = recv_exact(sock, length)
        if body is None:
            return None
            
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, struct.error, OSError):
        return None

def send_file(sock: socket.socket, filepath: str) -> None:
    """讀取檔案並發送 Raw Bytes"""
    file_size = os.path.getsize(filepath)
    with open(filepath, 'rb') as f:
        sent = 0
        while sent < file_size:
            chunk = f.read(4096)
            if not chunk: break
            sock.sendall(chunk)
            sent += len(chunk)

def recv_file(sock: socket.socket, save_path: str, file_size: int) -> None:
    """接收指定大小的 Raw Bytes 並寫入檔案"""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    received = 0
    with open(save_path, 'wb') as f:
        while received < file_size:
            chunk_size = min(4096, file_size - received)
            chunk = sock.recv(chunk_size)
            if not chunk: break
            f.write(chunk)
            received += len(chunk)