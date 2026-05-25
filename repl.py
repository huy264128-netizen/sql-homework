"""
图书管理系统 REPL —— 可扩展命令接口。

支持：
  - 直接输入 SQL 语句执行查询
  - 以 "." 开头的自定义命令（如 .help, .tables, .schema, .exit）
  - 通过 @register_command 装饰器从外部模块注册新命令

使用示例（外部模块注册新命令）:
    from repl import register_command

    @register_command("ai", help_text="使用AI操作数据库", aliases=["ask"])
    def cmd_ai(args: str) -> str:
        ...
"""

import init_database
from accessDB import exampleDB

# ---------------------------------------------------------------------------
# 命令注册表
# ---------------------------------------------------------------------------

_command_registry: dict[str, dict] = {}

__all__ = ["register_command", "main"]


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


# ---------------------------------------------------------------------------
# 内置命令
# ---------------------------------------------------------------------------

@register_command("help", help_text="显示此帮助信息", aliases=["h", "?"])
def cmd_help(_args: str) -> str:
    """列出所有已注册的命令及其帮助文本。"""
    lines: list[str] = []
    seen: set[str] = set()
    for cmd_name, entry in _command_registry.items():
        if cmd_name in seen:
            continue
        seen.add(cmd_name)
        lines.append(f"  .{cmd_name:<12} {entry['help']}")
    return "可用命令:\n" + "\n".join(sorted(lines))


@register_command("exit", help_text="退出 REPL", aliases=["quit", "q"])
def cmd_exit(_args: str) -> None:
    """退出 REPL。"""
    import sys
    print("再见！")
    sys.exit(0)


@register_command("tables", help_text="列出数据库中所有表", aliases=["tbl", "t"])
def cmd_tables(_args: str) -> str:
    """列出数据库中所有用户表。"""
    rows = exampleDB.execSQL(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    if not rows:
        return "(无表)"
    return "\n".join(row[0] for row in rows)


@register_command("schema", help_text="显示建表语句 (.schema [表名])", aliases=["sch"])
def cmd_schema(args: str) -> str:
    """显示建表语句，可选指定表名。"""
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

@register_command("borrow", help_text="借书 (.borrow [用户id] [书id])", aliases=["br"])
def cmd_borrow(args: str) -> str:
    """借书：插入一条 BORROW 记录，触发器自动更新 BOOK/USER 状态。"""
    parts = args.split()
    if len(parts) < 2:
        return "用法: .borrow [用户id] [书id]\n示例: .borrow 1 109"

    userid_str, bookid_str = parts[0], parts[1]

    # 验证输入为整数
    if not userid_str.isdigit() or not bookid_str.isdigit():
        return "错误: 用户id 和 书id 必须是整数"

    userid = int(userid_str)
    bookid = int(bookid_str)

    # 1. 获取用户信息（用于友好提示）
    user_check = exampleDB.execSQL(
        f"SELECT username FROM USER WHERE userid = {userid}"
    )
    if not user_check:
        return f"错误: 用户 {userid} 不存在"
    username = user_check[0][0]

    # 2. 获取书籍信息
    book_check = exampleDB.execSQL(
        f"SELECT bookname FROM BOOK WHERE bookid = {bookid}"
    )
    if not book_check:
        return f"错误: 书籍 {bookid} 不存在"
    bookname = book_check[0][0]

    # 3. 生成新的 borrowid
    max_id = exampleDB.execSQL("SELECT COALESCE(MAX(borrowid), 0) FROM BORROW")
    if not max_id:
        return "错误: 无法查询借阅记录"
    new_borrowid = max_id[0][0] + 1

    # 4. 执行 INSERT（触发器 trg_borrow_insert 自动校验并更新 BOOK/USER）
    try:
        exampleDB.execSQL(
            f"INSERT INTO BORROW (borrowid, userid, bookid) VALUES ({new_borrowid}, {userid}, {bookid})"
        )
        return f"借书成功! 用户 '{username}' 借阅了 '{bookname}'（借阅记录ID: {new_borrowid}）"
    except Exception as e:
        return f"借书失败: {e}"


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def main():
    """REPL 主入口。"""
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

        # 自定义命令解析（以 "." 开头）
        if user_input.startswith("."):
            parts = user_input.split(maxsplit=1)
            cmd_name = parts[0][1:]  # 去掉点号前缀
            cmd_args = parts[1] if len(parts) > 1 else ""

            if cmd_name in _command_registry:
                try:
                    result = _command_registry[cmd_name]["handler"](cmd_args)
                    if result is not None:
                        print(result)
                except SystemExit:
                    raise
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


if __name__ == "__main__":
    main()
