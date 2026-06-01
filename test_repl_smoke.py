# -*- coding: utf-8 -*-
"""REPL 冒烟测试 —— 通过 import 直接调用命令函数验证快捷指令。"""
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
from pathlib import Path

# 强制使用干净的测试库
Path("./example.db").unlink(missing_ok=True)

import init_database
init_database.initial()

from repl import _command_registry

def run_cmd(cmd_name: str, args: str = ""):
    """通过注册表调用命令函数，捕获输出。"""
    if cmd_name not in _command_registry:
        return f"[FAIL] 命令 '{cmd_name}' 未注册"
    try:
        result = _command_registry[cmd_name]["handler"](args)
        return result if result is not None else "(无输出)"
    except SystemExit:
        return "(exit)"
    except Exception as e:
        return f"[FAIL] {type(e).__name__}: {e}"

print("=" * 60)
print("REPL 冒烟测试")
print("=" * 60)

# 1. 帮助
print("\n--- .help ---")
print(run_cmd("help"))

# 2. 表列表
print("\n--- .tables ---")
print(run_cmd("tables"))

# 3. 排行（初始状态：有借阅数据）
print("\n--- .rank ---")
print(run_cmd("rank"))

# 4. 借书测试
print("\n--- .borrow 8 109 (Henry 借 The Odyssey) ---")
print(run_cmd("borrow", "8 109"))

# 5. 还书测试
print("\n--- .return 109 (归还 The Odyssey) ---")
print(run_cmd("return", "109"))

# 6. 添加用户
print("\n--- .adduser 张三 ---")
print(run_cmd("adduser", "张三"))

# 7. 添加书籍
print("\n--- .addbook 三体 ---")
print(run_cmd("addbook", "三体"))

# 8. 新用户借书
print("\n--- .borrow 张三 三体 ---")
print(run_cmd("borrow", "张三 三体"))

# 9. 查询借阅
print("\n--- .listborrow 张三 ---")
print(run_cmd("listborrow", "张三"))

# 10. 更新排行
print("\n--- .rank (新用户上榜) ---")
print(run_cmd("rank"))

# 11. 借书上限测试
print("\n--- .borrow 1 109 (Alice 已借2本，再借1本) ---")
print(run_cmd("borrow", "1 109"))

print("\n--- .borrow 1 110 (Alice 再借，应该第4本) ---")
print(run_cmd("borrow", "1 110"))

# 12. 还书后用书名还
print("\n--- .return '三体' (用书名归还) ---")
print(run_cmd("return", "三体"))

# 13. 模式（schema）
print("\n--- .schema USER ---")
print(run_cmd("schema", "USER"))

print("\n" + "=" * 60)
print("REPL 冒烟测试完成")
print("=" * 60)

# 清理
Path("./example.db").unlink(missing_ok=True)
