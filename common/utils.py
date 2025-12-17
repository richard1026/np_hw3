# common/utils.py

def input_int(prompt: str, min_val: int, max_val: int) -> int:
    """反覆讀整數，直到在 [min_val, max_val] 之間。"""
    while True:
        s = input(prompt).strip()
        try:
            v = int(s)
        except ValueError:
            print(f"請輸入整數 ({min_val}~{max_val})")
            continue
        if v < min_val or v > max_val:
            print(f"請輸入範圍內的數字 ({min_val}~{max_val})")
            continue
        return v
