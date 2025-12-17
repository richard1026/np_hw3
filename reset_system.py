import os
import shutil
from pathlib import Path

def clean_directory(path: Path, name: str):
    """清空指定目錄下的所有檔案與資料夾，但保留目錄本身"""
    if not path.exists():
        print(f"[INFO] {name} 目錄不存在 ({path})，跳過。")
        return
    
    print(f"正在清空 {name}...")
    deleted_count = 0
    try:
        for item in path.iterdir():
            # 忽略 .gitkeep 或隱藏檔 (視需求)
            if item.name.startswith("."):
                continue
                
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                deleted_count += 1
            except Exception as e:
                print(f"  [錯誤] 無法刪除 {item.name}: {e}")
        
        if deleted_count > 0:
            print(f"  - 已刪除 {deleted_count} 個項目。")
        else:
            print("  - 目錄原本就是空的。")
            
    except Exception as e:
        print(f"[錯誤] 無法存取目錄 {name}: {e}")

def reset_system():
    root = Path(__file__).resolve().parent
    
    print("=== 開始重置遊戲商城系統 ===")

    # 1. 刪除資料庫檔案 (Reset DB)
    db_file = root /"db_data.json"
    if db_file.exists():
        try:
            os.remove(db_file)
            print(f"[OK] 資料庫已刪除: {db_file}")
        except Exception as e:
            print(f"[錯誤] 無法刪除資料庫: {e}")
    else:
        print("[INFO] 未發現資料庫檔案，無需刪除。")

    # 2. 清空 Server 端的上架遊戲 (Reset Uploaded Games)

    server_storage = root / "server" / "storage"
    clean_directory(server_storage, "Server Storage (上架遊戲庫)")

    # 3. 清空 Player 端的下載遊戲 (Reset Player Downloads)

    player_downloads = root / "downloads"
    clean_directory(player_downloads, "Player Downloads (玩家下載庫)")

    

    print("\n=== 重置完成 ===")
    print("請記得重新啟動 Server 以讓變更生效。")

if __name__ == "__main__":
    print("警告：此操作將會永久刪除以下資料：")
    print("1. 所有使用者帳號、遊戲紀錄、評分 (db_data.json)")
    print("2. 伺服器端所有已上架的遊戲檔案 (server/storage)")
    print("3. 玩家端所有已下載的遊戲檔案 (player_client/downloads)")
    print("-" * 40)
    
    confirm = input("確定要執行重置嗎？(y/N): ").strip().lower()
    if confirm == 'y':
        reset_system()
    else:
        print("已取消操作。")