# -*- coding: utf-8 -*-
"""
图书管理系统 —— 综合自动化测试程序

覆盖范围：
  1. 表结构与约束（PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK）
  2. 触发器 trg_borrow_insert（插入时自动同步 + RAISE ABORT 防重复借出）
  3. 触发器 trg_borrow_delete（删除时自动恢复）
  4. Python 应用层存储过程（borrow_book / return_book / add_user / add_book）
  5. 事务原子性（ROLLBACK 全部撤销）
  6. 视图 V_USER_BORROW / V_BORROW_RANK
  7. REPL 快捷指令（.borrow / .return / .adduser / .addbook / .listborrow / .rank）

用法:
    python test_automated.py
"""
import sys
import io
import gc
import sqlite3
import traceback
from pathlib import Path

# Windows 控制台 UTF-8 补丁
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 复用 init_database 中的 SQL 定义，避免重复维护
from init_database import SCHEMA_SQL, SMALL_SEED_SQL, SEED_SQL, VIEWS_SQL, init_to_db

# ============================================================================
# 测试框架
# ============================================================================

_results: list[dict] = []

def _ok(name: str, detail: str = ""):
    _results.append({"name": name, "status": "PASS", "detail": detail})

def _fail(name: str, detail: str = ""):
    _results.append({"name": name, "status": "FAIL", "detail": detail})

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def new_db(*, with_data: bool = True) -> sqlite3.Connection:
    """创建全新的 :memory: 测试数据库。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.executescript(VIEWS_SQL)
    if with_data:
        conn.executescript(SMALL_SEED_SQL)
        conn.commit()
    return conn


# ============================================================================
# 第一部分：表结构与约束
# ============================================================================

def test_schema_constraints():
    section("第一部分：表结构与约束")

    conn = new_db()

    # 1.1 PRIMARY KEY 唯一性
    try:
        conn.execute("INSERT INTO USER (userid, username) VALUES (1, 'Duplicate')")
        _fail("1.1", "PRIMARY KEY — userid 重复应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.1", "PRIMARY KEY — userid=1 重复正确拒绝")

    # 1.2 UNIQUE 约束 — username
    try:
        conn.execute("INSERT INTO USER (userid, username) VALUES (4, 'Alice')")
        _fail("1.2", "UNIQUE — username='Alice' 重复应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.2", "UNIQUE — username 重复正确拒绝")

    # 1.3 UNIQUE 约束 — bookname
    try:
        conn.execute("INSERT INTO BOOK (bookid, bookname) VALUES (201, 'SQL 入门')")
        _fail("1.3", "UNIQUE — bookname 重复应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.3", "UNIQUE — bookname 重复正确拒绝")

    # 1.4 FOREIGN KEY — userid 不存在
    try:
        conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 999, 101)")
        _fail("1.4", "FOREIGN KEY — userid=999 不存在应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.4", "FOREIGN KEY — 不存在的 userid 正确拒绝")

    # 1.5 FOREIGN KEY — bookid 不存在
    try:
        conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 999)")
        _fail("1.5", "FOREIGN KEY — bookid=999 不存在应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.5", "FOREIGN KEY — 不存在的 bookid 正确拒绝")

    # 1.6 CHECK 约束 — BOOK.status
    try:
        conn.execute("INSERT INTO BOOK (bookid, bookname, status) VALUES (201, 'Test', 'invalid')")
        _fail("1.6", "CHECK — BOOK.status='invalid' 应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.6", "CHECK — 非法 BOOK.status 正确拒绝")

    # 1.7 CHECK 约束 — USER.currentborrow 上限
    try:
        conn.execute("UPDATE USER SET currentborrow = 6 WHERE userid = 1")
        _fail("1.7", "CHECK — currentborrow=6 (超上限) 应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.7", "CHECK — currentborrow 超上限 (6) 正确拒绝")

    # 1.8 CHECK 约束 — USER.currentborrow 负数
    try:
        conn.execute("UPDATE USER SET currentborrow = -1 WHERE userid = 1")
        _fail("1.8", "CHECK — currentborrow=-1 应被拒绝")
    except sqlite3.IntegrityError:
        _ok("1.8", "CHECK — currentborrow 负数正确拒绝")

    # 1.9 正常插入验证
    conn.execute("INSERT INTO USER (userid, username) VALUES (4, 'Diana')")
    conn.execute("INSERT INTO BOOK (bookid, bookname) VALUES (201, '新书')")
    conn.commit()
    u = conn.execute("SELECT username FROM USER WHERE userid=4").fetchone()
    b = conn.execute("SELECT bookname FROM BOOK WHERE bookid=201").fetchone()
    if u and u[0] == 'Diana' and b and b[0] == '新书':
        _ok("1.9", "正常 INSERT — 合法数据正确插入")
    else:
        _fail("1.9", f"真实: u={u}, b={b}")

    conn.close()


# ============================================================================
# 第二部分：触发器 trg_borrow_insert
# ============================================================================

def test_trigger_insert():
    section("第二部分：触发器 trg_borrow_insert")

    conn = new_db()

    # 2.1 正常借书 — BOOK.status → 'borrowed', USER.currentborrow +1
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101)")
    conn.commit()
    s = conn.execute("SELECT status FROM BOOK WHERE bookid=101").fetchone()[0]
    c = conn.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    if s == 'borrowed' and c == 1:
        _ok("2.1", "正常借书 — status='borrowed', currentborrow=1")
    else:
        _fail("2.1", f"status={s}, currentborrow={c}")

    # 2.2 重复借同一本书 → RAISE ABORT
    try:
        conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 2, 101)")
        _fail("2.2", "重复借书 — RAISE ABORT 应拦截")
    except sqlite3.IntegrityError as e:
        _ok("2.2", f"RAISE ABORT 正确拦截: {e}")

    # 2.3 多用户借不同书，互不影响
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 2, 102)")
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (3, 3, 103)")
    conn.commit()
    a = conn.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    b = conn.execute("SELECT currentborrow FROM USER WHERE userid=2").fetchone()[0]
    ch = conn.execute("SELECT currentborrow FROM USER WHERE userid=3").fetchone()[0]
    if a == 1 and b == 1 and ch == 1:
        _ok("2.3", "多用户借不同书 — currentborrow 各自独立 (1,1,1)")
    else:
        _fail("2.3", f"Alice={a}, Bob={b}, Charlie={ch}")

    # 2.4 同一用户借多本书（用全新 DB 避免冲突）
    conn2 = new_db()
    conn2.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101)")
    conn2.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 1, 102)")
    conn2.commit()
    c = conn2.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    bs = conn2.execute("SELECT COUNT(*) FROM BOOK WHERE status='borrowed'").fetchone()[0]
    if c == 2 and bs == 2:
        _ok("2.4", "同一用户借多书 — currentborrow=2, 2本书 borrowed")
    else:
        _fail("2.4", f"currentborrow={c}, books_borrowed={bs}")
    conn2.close()

    # 2.5 借书达上限 5 后不能再借
    conn3 = new_db(with_data=False)
    conn3.executescript("""
        INSERT INTO USER (userid, username) VALUES (1, 'Alice');
        INSERT INTO BOOK (bookid, bookname) VALUES (101,'B1'),(102,'B2'),(103,'B3'),(104,'B4'),(105,'B5'),(106,'B6');
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1,1,101),(2,1,102),(3,1,103),(4,1,104),(5,1,105);
    """)
    conn3.commit()
    c5 = conn3.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    if c5 != 5:
        _fail("2.5", f"前置条件不符: currentborrow={c5} (应为5)")
    else:
        try:
            conn3.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (6, 1, 106)")
            conn3.commit()
            post_c = conn3.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
            _fail("2.5", f"第6本未被阻止! currentborrow={post_c}")
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            _ok("2.5", "借书上限 — 第6本被 CHECK/触发器正确阻止")
    conn3.close()

    conn.close()


# ============================================================================
# 第三部分：触发器 trg_borrow_delete
# ============================================================================

def test_trigger_delete():
    section("第三部分：触发器 trg_borrow_delete")

    conn = new_db()
    conn.executescript("""
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101);
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 1, 102);
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (3, 2, 103);
    """)
    conn.commit()

    # 3.1 正常还书
    conn.execute("DELETE FROM BORROW WHERE bookid=101")
    conn.commit()
    s = conn.execute("SELECT status FROM BOOK WHERE bookid=101").fetchone()[0]
    c = conn.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    bc = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid=1").fetchone()[0]
    if s == 'returned' and c == 1 and bc == 1:
        _ok("3.1", "正常还书 — status='returned', currentborrow 从2减为1")
    else:
        _fail("3.1", f"status={s}, currentborrow={c}, borrow_count={bc}")

    # 3.2 还清所有书
    conn.execute("DELETE FROM BORROW WHERE bookid=102")
    conn.commit()
    c = conn.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    if c == 0:
        _ok("3.2", "还清所有书 — Alice currentborrow=0")
    else:
        _fail("3.2", f"currentborrow={c}")

    # 3.3 还另一用户的书
    conn.execute("DELETE FROM BORROW WHERE bookid=103")
    conn.commit()
    c2 = conn.execute("SELECT currentborrow FROM USER WHERE userid=2").fetchone()[0]
    if c2 == 0:
        _ok("3.3", "还另一用户的书 — Bob currentborrow 归0")
    else:
        _fail("3.3", f"currentborrow={c2}")

    conn.close()


# ============================================================================
# 第四部分：应用层存储过程（事务原子性）
# ============================================================================

def test_stored_procedures():
    section("第四部分：应用层存储过程（事务原子性）")

    # 创建文件数据库供 accessDB 使用（通过 init_to_db 走完整的初始化路径）
    DB_FILE = Path("./_test_sp.db")
    if DB_FILE.exists():
        DB_FILE.unlink()

    import accessDB
    original_path = accessDB.dbPath
    accessDB.dbPath = DB_FILE
    db = accessDB.accessDB(DB_FILE)
    init_to_db(db, SMALL_SEED_SQL)

    # 4.1 borrow_book — 正常借书
    bid, username, bookname = db.borrow_book(1, 101)
    if username == 'Alice' and bookname == 'SQL 入门' and bid > 0:
        _ok("4.1", f"borrow_book 返回 (bid={bid}, user={username}, book={bookname})")
    else:
        _fail("4.1", f"返回值: ({bid}, {username}, {bookname})")

    # 4.2 borrow_book — 书已被借
    try:
        db.borrow_book(2, 101)
        _fail("4.2", "已借出的书应抛 ValueError")
    except ValueError as e:
        _ok("4.2", f"已借出书抛 ValueError: {e}")

    # 4.3 borrow_book — 用户不存在
    try:
        db.borrow_book(999, 102)
        _fail("4.3", "不存在用户应抛 ValueError")
    except ValueError:
        _ok("4.3", "不存在用户抛 ValueError")

    # 4.4 return_book — 正常还书
    username, bookname = db.return_book(101)
    verify_conn = sqlite3.connect(str(DB_FILE))
    verify_conn.execute("PRAGMA foreign_keys = ON")
    s = verify_conn.execute("SELECT status FROM BOOK WHERE bookid=101").fetchone()[0]
    c = verify_conn.execute("SELECT currentborrow FROM USER WHERE userid=1").fetchone()[0]
    verify_conn.close()
    if username == 'Alice' and s == 'returned' and c == 0:
        _ok("4.4", f"return_book — 状态正确恢复 ({username}, status={s}, cur={c})")
    else:
        _fail("4.4", f"username={username}, status={s}, currentborrow={c}")

    # 4.5 return_book — 未借出的书
    try:
        db.return_book(101)
        _fail("4.5", "未借出的书应抛 ValueError")
    except ValueError:
        _ok("4.5", "未借出书抛 ValueError")

    # 4.6 add_user — 正常添加
    new_id = db.add_user('Diana')
    vc = sqlite3.connect(str(DB_FILE))
    u = vc.execute("SELECT username FROM USER WHERE userid=?", (new_id,)).fetchone()
    vc.close()
    if u and u[0] == 'Diana':
        _ok("4.6", f"add_user — Diana 正确插入 (userid={new_id})")
    else:
        _fail("4.6", f"new_id={new_id}, found={u}")

    # 4.7 add_user — 用户名重复
    try:
        db.add_user('Alice')
        _fail("4.7", "重复用户名应抛 ValueError")
    except ValueError:
        _ok("4.7", "重复用户名抛 ValueError")

    # 4.8 add_book — 正常添加
    new_bid = db.add_book('新书推荐')
    vc = sqlite3.connect(str(DB_FILE))
    b = vc.execute("SELECT bookname FROM BOOK WHERE bookid=?", (new_bid,)).fetchone()
    vc.close()
    if b and b[0] == '新书推荐':
        _ok("4.8", f"add_book — 新书正确插入 (bookid={new_bid})")
    else:
        _fail("4.8", f"new_bid={new_bid}, found={b}")

    # 4.9 add_book — 书名重复
    try:
        db.add_book('SQL 入门')
        _fail("4.9", "重复书名应抛 ValueError")
    except ValueError:
        _ok("4.9", "重复书名抛 ValueError")

    # 4.10 事务原子性 — ROLLBACK 验证
    conn3 = sqlite3.connect(str(DB_FILE))
    conn3.execute("PRAGMA foreign_keys = ON")
    conn3.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (10, 1, 102)")
    conn3.commit()
    conn3.close()
    try:
        db.borrow_book(2, 102)  # 应该失败（已被Alice借走）
    except ValueError:
        pass
    # 验证 Bob 状态未被污染
    vc = sqlite3.connect(str(DB_FILE))
    c2 = vc.execute("SELECT currentborrow FROM USER WHERE userid=2").fetchone()[0]
    vc.close()
    if c2 == 0:
        _ok("4.10", "事务原子性 — 异常后 Bob 状态未污染 (currentborrow=0)")
    else:
        _fail("4.10", f"Bob currentborrow={c2}，应保持0")

    del db
    gc.collect()
    accessDB.dbPath = original_path
    if DB_FILE.exists():
        DB_FILE.unlink()


# ============================================================================
# 第五部分：视图
# ============================================================================

def test_views():
    section("第五部分：视图 V_USER_BORROW / V_BORROW_RANK")

    conn = new_db()
    conn.executescript("""
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101);
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 1, 102);
        INSERT INTO BORROW (borrowid, userid, bookid) VALUES (3, 2, 103);
    """)
    conn.commit()

    # 5.1 V_USER_BORROW
    rows = conn.execute(
        "SELECT username, bookid, bookname FROM V_USER_BORROW WHERE userid=1"
    ).fetchall()
    if len(rows) == 2 and all(r[0] == 'Alice' for r in rows):
        _ok("5.1", f"V_USER_BORROW — Alice 2条借阅记录: {[(r[1], r[2]) for r in rows]}")
    else:
        _fail("5.1", f"rows={rows}")

    # 5.2 V_BORROW_RANK
    rows = conn.execute("SELECT * FROM V_BORROW_RANK").fetchall()
    if rows and rows[0] == ('Alice', 2):
        _ok("5.2", f"V_BORROW_RANK — 第一是 Alice(2本), top3={rows[:3]}")
    else:
        _fail("5.2", f"first row={rows[0] if rows else 'empty'}")

    # 5.3 视图实时更新
    conn.execute("DELETE FROM BORROW WHERE bookid=102")
    conn.commit()
    rows = conn.execute("SELECT * FROM V_BORROW_RANK").fetchall()
    alice = [r for r in rows if r[0] == 'Alice']
    if alice and alice[0][1] == 1:
        _ok("5.3", "V_BORROW_RANK 实时更新 — Alice 从2降为1")
    else:
        _fail("5.3", f"Alice rank={alice}")

    conn.close()


# ============================================================================
# 第六部分：REPL 快捷指令
# ============================================================================

def test_repl_commands():
    section("第六部分：REPL 快捷指令集成测试")

    DB_FILE = Path("./_test_repl.db")
    if DB_FILE.exists():
        DB_FILE.unlink()

    import accessDB
    original_path = accessDB.dbPath
    accessDB.dbPath = DB_FILE

    # 替换 repl 模块中的 exampleDB，使其指向测试数据库
    import repl
    repl.exampleDB = accessDB.accessDB(DB_FILE)
    init_to_db(repl.exampleDB, SMALL_SEED_SQL)

    from repl import _command_registry

    def run(cmd: str, args: str = "") -> str:
        if cmd not in _command_registry:
            return f"[FAIL] unknown '{cmd}'"
        try:
            result = _command_registry[cmd]["handler"](args)
            return result if result is not None else ""
        except SystemExit:
            return "(exit)"
        except Exception as e:
            return f"[ERROR] {type(e).__name__}: {e}"

    # 6.1 .borrow ID 方式
    r = run("borrow", "1 101")
    if "借书成功" in r and "Alice" in r:
        _ok("6.1", f".borrow ID — {r}")
    else:
        _fail("6.1", r)

    # 6.2 .borrow 用户名+书名
    r = run("borrow", "Bob 'Python 进阶'")
    if "借书成功" in r and "Bob" in r:
        _ok("6.2", f".borrow 名称 — {r}")
    else:
        _fail("6.2", r)

    # 6.3 .borrow 重复借
    r = run("borrow", "3 101")
    if "借书失败" in r:
        _ok("6.3", f".borrow 重复 — {r}")
    else:
        _fail("6.3", r)

    # 6.4 .return ID
    r = run("return", "101")
    if "还书成功" in r and "Alice" in r:
        _ok("6.4", f".return ID — {r}")
    else:
        _fail("6.4", r)

    # 6.5 .return 书名（需加引号，因为 _parse_quoted_args 按空格分词）
    r = run("return", "'Python 进阶'")
    if "还书成功" in r and "Bob" in r:
        _ok("6.5", f".return 书名 — {r}")
    else:
        _fail("6.5", r)

    # 6.6 .adduser
    r = run("adduser", "张三")
    if "用户添加成功" in r and "张三" in r:
        _ok("6.6", f".adduser — {r}")
    else:
        _fail("6.6", r)

    # 6.7 .addbook
    r = run("addbook", "三体")
    if "书籍添加成功" in r and "三体" in r:
        _ok("6.7", f".addbook — {r}")
    else:
        _fail("6.7", r)

    # 6.8 .listborrow（Alice 在 6.1 借了书但 6.4 已还，所以可能"没有借阅"）
    r = run("listborrow", "Alice")
    if "Alice" in r or "没有" in r:
        _ok("6.8", f".listborrow — 查询成功: {r}")
    else:
        _fail("6.8", r)

    # 6.9 .rank
    r = run("rank", "")
    if "排行" in r:
        _ok("6.9", f".rank — 排行显示")
    else:
        _fail("6.9", r)

    # 6.10 .tables
    r = run("tables", "")
    if "BOOK" in r and "USER" in r and "BORROW" in r:
        _ok("6.10", ".tables — 列出所有表")
    else:
        _fail("6.10", r)

    accessDB.dbPath = original_path
    repl.exampleDB = accessDB.exampleDB  # 恢复原始实例
    gc.collect()
    if DB_FILE.exists():
        DB_FILE.unlink()


# ============================================================================
# 主入口 & 报告生成
# ============================================================================

TEST_SECTIONS = [
    ("1. 表结构与约束", test_schema_constraints),
    ("2. 触发器 trg_borrow_insert", test_trigger_insert),
    ("3. 触发器 trg_borrow_delete", test_trigger_delete),
    ("4. 应用层存储过程", test_stored_procedures),
    ("5. 视图", test_views),
    ("6. REPL 快捷指令", test_repl_commands),
]


def print_report():
    passed = sum(1 for r in _results if r["status"] == "PASS")
    failed = sum(1 for r in _results if r["status"] == "FAIL")
    total = len(_results)

    print("\n\n")
    print("=" * 70)
    print("              测试结果汇总")
    print("=" * 70)
    print(f"  总计: {total}  |  PASS: {passed}  |  FAIL: {failed}  |  {'ALL PASS!' if failed == 0 else 'SOME FAILED!'}")
    print("=" * 70)

    for i, r in enumerate(_results, 1):
        icon = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
        line = f"  {i:02d}. {icon} {r['name']}"
        if r["detail"]:
            line += f"  —  {r['detail']}"
        print(line)

    print("=" * 70)
    return passed, failed, total


def main():
    print("=" * 70)
    print("  图书管理系统 — 综合自动化测试")
    print("=" * 70)

    for label, func in TEST_SECTIONS:
        try:
            func()
        except Exception:
            _fail(f"{label} 异常", traceback.format_exc())

    passed, failed, total = print_report()

    if failed > 0:
        print(f"\n{failed} 个测试失败!")
        sys.exit(1)
    else:
        print(f"\n全部 {total} 个测试通过!")
        sys.exit(0)


if __name__ == "__main__":
    main()
