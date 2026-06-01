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

import shlex

import init_database
from accessDB import exampleDB


def _parse_quoted_args(args: str) -> list[str]:
    """
    解析命令行参数，支持用引号包裹含空格的参数。
    例如: Alice 'The Great Gatsby' → ['Alice', 'The Great Gatsby']
    """
    try:
        return shlex.split(args)
    except ValueError:
        # shlex 解析失败时退化为简单 split
        return args.split()


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

@register_command("borrow", help_text="借书 (.borrow [用户id/用户名] [书id/书名])", aliases=["br"])
def cmd_borrow(args: str) -> str:
    """借书：支持 ID（整数）和名称（字符串）。调用 borrow_book()。"""
    # 按空格拆分为两个参数，但允许书名/用户名含空格（用引号包裹）
    parts = _parse_quoted_args(args)
    if len(parts) < 2:
        return "用法: .borrow [用户id/用户名] [书id/书名]\n示例: .borrow 1 109\n示例: .borrow Alice 'The Great Gatsby'"

    user_input, book_input = parts[0], parts[1]

    # 解析用户：整数→userid，否则→按用户名查找
    if user_input.isdigit():
        userid = int(user_input)
    else:
        userid = exampleDB.get_user_id(user_input)

    # 解析书籍：整数→bookid，否则→按书名查找
    if book_input.isdigit():
        bookid = int(book_input)
    else:
        bookid = exampleDB.get_book_id(book_input)

    try:
        bid, username, bookname = exampleDB.borrow_book(userid, bookid)
        return f"借书成功! 用户 '{username}' 借阅了 '{bookname}'（借阅记录ID: {bid}）"
    except Exception as e:
        return f"借书失败: {e}"


@register_command("return", help_text="还书 (.return [书id/书名])", aliases=["rt"])
def cmd_return(args: str) -> str:
    """还书：支持 ID（整数）和书名（字符串）。调用 return_book()。"""
    args = args.strip()
    if not args:
        return "用法: .return [书id/书名]\n示例: .return 109\n示例: .return 'The Great Gatsby'"

    # 先用 _parse_quoted_args 解析（支持引号包裹的书名），取第一个参数
    parts = _parse_quoted_args(args)
    book_input = parts[0]

    # 解析书籍：整数→bookid，否则→按书名查找
    if book_input.isdigit():
        bookid = int(book_input)
    else:
        bookid = exampleDB.get_book_id(book_input)

    try:
        username, bookname = exampleDB.return_book(bookid)
        return f"还书成功! 用户 '{username}' 归还了 '{bookname}'"
    except Exception as e:
        return f"还书失败: {e}"


@register_command("listborrow", help_text="查询用户借阅了哪些书 (.listborrow [用户id/用户名])", aliases=["lb"])
def cmd_listborrow(args: str) -> str:
    """通过视图 V_USER_BORROW 查询指定用户当前借阅的所有书籍。支持 ID 和用户名。"""
    args = args.strip()
    if not args:
        return "用法: .listborrow [用户id/用户名]\n示例: .listborrow 1\n示例: .listborrow Alice"

    # 解析用户：整数→userid，否则→按用户名查找
    if args.isdigit():
        userid = int(args)
    else:
        userid = exampleDB.get_user_id(args)

    # 直接从视图查询（视图 V_USER_BORROW 已预 JOIN USER、BORROW、BOOK 三表）
    rows = exampleDB.execSQL(
        f"SELECT username, bookid, bookname FROM V_USER_BORROW WHERE userid = {userid}"
    )
    if not rows:
        return f"用户 {userid} 当前没有借阅任何书籍"

    username = rows[0][0]
    lines = [f"用户 '{username}' 当前借阅:"]
    for row in rows:
        lines.append(f"  [{row[1]}] {row[2]}")
    return "\n".join(lines)

@register_command("adduser", help_text="添加新用户 (.adduser [用户名])", aliases=["au"])
def cmd_adduser(args: str) -> str:
    """添加新用户：调用 accessDB.add_user()。"""
    args = args.strip()
    if not args:
        return "用法: .adduser [用户名]\n示例: .adduser 张三"
    try:
        new_id = exampleDB.add_user(args)
        return f"用户添加成功! userid={new_id}, username='{args}'"
    except Exception as e:
        return f"添加用户失败: {e}"


@register_command("addbook", help_text="添加新书籍 (.addbook [书名])", aliases=["ab"])
def cmd_addbook(args: str) -> str:
    """添加新书籍：调用 accessDB.add_book()。"""
    args = args.strip()
    if not args:
        return "用法: .addbook [书名]\n示例: .addbook 三体"
    try:
        new_id = exampleDB.add_book(args)
        return f"书籍添加成功! bookid={new_id}, bookname='{args}'"
    except Exception as e:
        return f"添加书籍失败: {e}"


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
