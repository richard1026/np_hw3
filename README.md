# Network Programming Final Project 

---

## Table of Contents

1. [環境需求](#-環境需求)
2. [專案結構](#-專案結構)
3. [連線與 IP 設定 (重要!)](#-連線與-ip-設定-重要)
4. [快速啟動指南](#-快速啟動指南)
5. [Demo 操作流程 (Step-by-Step)](#-demo-操作流程-step-by-step)

   * [1. 系統重置](#1-系統重置)
   * [2. 開發者：上架遊戲](#2-開發者上架遊戲)
   * [3. 玩家：下載與遊玩](#3-玩家下載與遊玩)
   * [4. 加分項目：Plugin（聊天室）](#4-加分項目plugin聊天室)


---

## 🛠 環境需求

* **Python 3.8+**
* **Pygame**（用於 GUI 遊戲顯示）

**安裝依賴：**

```bash
pip install pygame
```

---

## 專案結構

請確保您的檔案目錄結構如下：

```text
NP_HW3/
├── server/                  # [伺服器端]
│   ├── main_server.py       # 核心伺服器 (處理 Lobby, Dev, Game 邏輯)
│   ├── db_server.py         # 資料庫伺服器 (JSON persistency)
│   └── storage/             # [自動生成] 存放開發者上傳的遊戲檔案
├── developer_client/        # [開發者端]
│   └── developer_client.py  # 開發者介面 (上架 / 更新 / 下架)
├── player_client/           # [玩家端]
│   ├── lobby_client.py      # 玩家介面 (商店 / 大廳 / 聊天 / 啟動)
│   └── downloads/           # [自動生成] 玩家下載的遊戲 (依帳號隔離)
├── games/                   # [遊戲範本] (供上傳用)
│   ├── gomoku/              # 五子棋 (GUI, 2 人)
│   ├── chase_gui/           # 鬼抓人 (GUI, 3 人)
│   └── tictactoe/           # 井字遊戲 (CLI, 2 人)
├── plugins/                 # [擴充功能]
│   └── Chat/                # 聊天室 Plugin (Tkinter 視窗)
│       └── main.py
├── common/                  # [共用模組]
│   ├── protocol.py          # 通訊協定 (Length-Prefixed Framing)
│   └── utils.py             # 工具函式 (Input validation)
└── reset_system.py          # 系統重置腳本 (Demo 前清除資料用)
```

---

## ⚙️ 連線與 IP 設定

### Server 端（`server/main_server.py`）

* 找到 `game_host` 變數（或在 `player_create_room` 函式中）。
* 將預設的IP 改為 Server 的實體 IP（例如 `140.113.x.x`）。
* 若遇到撞port等情形，找到 `port`或`db_port`變數並修改

### Client 端（`developer_client.py` & `lobby_client.py`）

* 找到 `SERVER_HOST` 變數。
* 修改為 Server 的實體 IP。
* 若遇到撞port等情形，找到 `port`變數並修改
---

##  快速啟動指南

請依照順序開啟 **4 個終端機視窗** 執行：

### 1. 啟動 Database Server

```bash
python server/db_server.py
```

### 2. 啟動 Main Server

```bash
python server/main_server.py
```

### 3. 啟動 Developer Client

```bash
python developer_client/developer_client.py
```

### 4. 啟動 Player Client

（可開啟多個視窗模擬 P1, P2, P3）

```bash
python player_client/lobby_client.py
```

---

##  Demo 操作流程 (Step-by-Step)

### 1. 系統重置

**目的：** 確保 Demo 環境乾淨，清除舊帳號與檔案。

```bash
python reset_system.py
# 輸入 'y' 確認
```

>  重置後請務必 **重啟 DB Server 與 Main Server**。

---

### 2. 開發者：上架遊戲

1. 在 Developer Client 選擇 **1. Register** 註冊並登入（例如 `dev / dev`）。
2. 進入 **2. Manage Games → 1. Publish New Game**。

**輸入範例資訊：**

* Name: `Gomoku`
* Version: `1.0.0`
* Type: `GUI`
* Max Players: `2`
* 檔案路徑（關鍵）：`games/gomoku/main.py`

> 注意：必須指向 **.py 檔案**，不能是資料夾。


---

### 3. 玩家：下載與遊玩

1. 在 Player Client 註冊並登入（例如 `p1 / p1`）。

#### 下載遊戲

* 選擇 **1. Game Store → 3. Download / Update**。
* 輸入遊戲 ID 進行下載。

#### 建立房間

* 選擇 **2. Lobby → 2. Create Room**。
* 輸入遊戲 ID。

#### 加入房間

* 開啟第二個 Player Client（例如 `p2 / p2`）。
* 選擇 **2. Lobby → 3. Join Room**。
* 輸入房間 ID。

#### 開始遊戲

* 當人數到齊（Gomoku 2 人、Chase 3 人）時，Server 會自動廣播開始。
* 遊戲視窗彈出，即可遊玩。

---

### 4. 加分項目：Plugin（聊天室）

本系統支援 **動態掛載 Plugin**，不影響主遊戲流程。

#### 安裝插件

* 在 Player Client 主選單選擇 **3. Plugin Management**。
* 選擇 **1. Install Plugin** → 輸入編號安裝 **Room Chat Plugin**。

#### 驗證效果

* 建立或加入房間時，會自動彈出一個 **白色聊天室視窗**。
* 在聊天室輸入文字，同房且有安裝插件的玩家皆可看到。

#### 相容性

* 未安裝插件的玩家（Use Case PL4）仍可正常遊戲，只是看不到聊天室。

#### 生命週期

* 當房間解散時，聊天室視窗會自動關閉。

---

