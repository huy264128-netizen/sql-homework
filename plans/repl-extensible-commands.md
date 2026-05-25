# REPL 可扩展命令机制设计方案

## 一、设计目标

将当前仅支持 SQL 直通的 [`repl.py`](repl.py:1) 改造为支持「自定义命令 + SQL fallback」的可扩展 REPL，其他模块（如 [`aitui.py`](aitui.py:1)）可以通过简单的装饰器注册新命令。

## 二、架构概览

```
用户输入
    │
    ▼
┌──────────────┐
│   命令解析器   │  判断是「自定义命令」还是「SQL语句」
└──────┬───────┘
       │
       ├── 以 "." 开头 → 查找命令注册表 → 调用注册的 handler
       │
       └── 其它 → fallback 到 exampleDB.execSQL()
```

**命令统一以 `.` 开头**（类似 SQLite CLI），如 `.help`、`.tables`、`.exit`，这样不会和 SQL 语句冲突。

## 三、核心接口设计

### 3.1 命令注册装饰器

提供一个 `@register_command` 装饰器，任何模块 import 后即可注册命令：

```python
# repl.py

_command_registry: dict[str, dict] = {}

def register_command(name: str, help_text: str = "", aliases: list[str] | None = None):
    """
    命令注册装饰器。
    
    参数:
        name:      命令名（不含点号前缀），如 "tables"
        help_text: 帮助文本，显示在 .help 中
        aliases:   命令别名列表，如 ["tbl", "t"]
    
    使用示例:
        @register_command("tables", help_text="列出数据库中所有表", aliases=["tbl"])
        def cmd_tables(args: str) -> str:
            ...
    """
    def decorator(func):
        entry = {"handler": func, "help": help_text, "aliases": aliases or []}
        _command_registry[name] = entry
        for alias in aliases or []:
            _command_registry[alias] = entry
        return func
    return decorator
```

### 3.2 命令 handler 签名

所有命令函数统一签名：

```python
def cmd_xxx(args: str) -> Optional[str]:
    """
    参数:
        args: 命令后的参数字符串（去除命令名后的剩余部分），可能为空字符串
    返回:
        要打印的输出字符串；返回 None 表示无输出
    """
```

### 3.3 REPL 主循环

```python
def main():
    init_database.initial()
    print("图书管理系统 REPL。输入 .help 查看帮助，输入 .exit 退出。")
    
    while True:
        try:
            user_input = input("repl> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        
        if not user_input:
            continue
        
        # 自定义命令解析
        if user_input.startswith("."):
            parts = user_input.split(maxsplit=1)
            cmd_name = parts[0][1:]  # 去掉点号前缀
            cmd_args = parts[1] if len(parts) > 1 else ""
            
            if cmd_name in _command_registry:
                try:
                    result = _command_registry[cmd_name]["handler"](cmd_args)
                    if result is not None:
                        print(result)
                except Exception as e:
                    print(f"命令执行出错: {e}")
            else:
                print(f"未知命令: {cmd_name}，输入 .help 查看可用命令")
        else:
            # SQL fallback
            try:
                result = exampleDB.execSQL(user_input)
                print(result)
            except Exception as e:
                print(f"SQL 执行出错: {e}")
```

## 四、内置命令清单

| 命令 | 别名 | 功能 |
|------|------|------|
| `.help` | `.h` , `.?` | 列出所有已注册的命令及其帮助文本 |
| `.exit` | `.quit` , `.q` | 退出 REPL |
| `.tables` | `.tbl` , `.t` | 列出数据库中所有表名 |
| `.schema` | `.sch` | 列出指定表（或全部表）的 CREATE TABLE 语句 |

### 4.1 `.help` 实现

```python
@register_command("help", help_text="显示此帮助信息", aliases=["h", "?"])
def cmd_help(args: str) -> str:
    lines = ["可用命令:"]
    seen = set()
    for name, entry in _command_registry.items():
        if name not in seen:
            seen.add(name)
            lines.append(f"  .{name:<12} {entry['help']}")
    return "\n".join(lines)
```

### 4.2 `.tables` 实现

```python
@register_command("tables", help_text="列出数据库中所有表", aliases=["tbl", "t"])
def cmd_tables(args: str) -> str:
    rows = exampleDB.execSQL(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    if not rows:
        return "(无表)"
    return "\n".join(row[0] for row in rows)
```

### 4.3 `.schema` 实现

```python
@register_command("schema", help_text="显示建表语句 (.schema [表名])", aliases=["sch"])
def cmd_schema(args: str) -> str:
    if args:
        rows = exampleDB.execSQL(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{args}'"
        )
    else:
        rows = exampleDB.execSQL(
            "SELECT sql FROM sqlite_master WHERE type='table'"
        )
    if not rows:
        return "(无匹配)"
    return "\n".join(row[0] for row in rows if row[0])
```

### 4.4 `.exit` 实现

```python
@register_command("exit", help_text="退出 REPL", aliases=["quit", "q"])
def cmd_exit(args: str) -> str:
    import sys
    print("再见！")
    sys.exit(0)
```

## 五、外部模块扩展方式

其他模块（如 `aitui.py`）可以这样注册新命令：

```python
# 在 aitui.py 中
from repl import register_command

@register_command("ai", help_text="使用 AI 自然语言操作数据库", aliases=["ask"])
def cmd_ai(args: str) -> str:
    """将自然语言转为 SQL 并执行"""
    if not args:
        return "请提供问题描述，例如: .ai 查询所有已借出的书"
    response = agent.invoke(
        {"messages": [{"role": "user", "content": args}]},
        config=config,
        context=Context(user_id="1")
    )
    return response["messages"][-1].content
```

## 六、改造后的 repl.py 完整结构

```
repl.py
├── 导入区 (init_database, accessDB)
├── 命令注册表 _command_registry: dict
├── register_command() 装饰器工厂
├── 4 个内置命令函数 (help, exit, tables, schema)
├── main() 主循环
└── __name__ == '__main__' 入口
```

## 七、与现有代码的兼容性

- 现有的 SQL 直接输入 `SELECT * FROM BOOK` 完全保留，作为 fallback
- 唯一的行为变化：输入需要以 `.` 开头的才被视为自定义命令
- `exit` 不再直接识别（因为不包含 `.`），用户使用 `.exit` 或 `.q` 退出

## 八、待确认事项

1. **命令前缀**：使用 `.` 作为命令前缀是否合适？（与 SQLite CLI 一致）
2. **是否需要保留无前缀的 `exit` 识别**（向后兼容）？
3. **是否需要 `register_command` 导出到 `__all__` 以便 IDE 自动补全？**
