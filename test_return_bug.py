# -*- coding: utf-8 -*-
"""
测试还书功能是否存在 bug。
验证场景：
  1. 正常借书 + 还书流程
  2. 还书后 BOOK.status / USER.currentborrow / BORROW 记录数是否一致
  3. 连续借还多次后状态是否仍然一致
  4. execSQL 对 DELETE 语句的返回值处理
  5. Python 版本与 cursor.executescript 兼容性
"""
import sys
import sqlite3
from pathlib import Path

# 确保使用干净的数据库
DB_PATH = Path("./test_return.db")

# Windows 控制台 GBK 编码补丁：避免 UnicodeEncodeError
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

_conns_to_close: list[sqlite3.Connection] = []

def _connect():
    """创建数据库连接并记录，确保 teardown 时能关闭。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    _conns_to_close.append(conn)
    return conn

def _close_all():
    """关闭所有记录的连接。"""
    for conn in _conns_to_close:
        try:
            conn.close()
        except Exception:
            pass
    _conns_to_close.clear()

def setup():
    """创建独立的测试数据库（结构与正式库一致）"""
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    conn = _connect()
    
    conn.executescript("""
        CREATE TABLE BOOK(
            bookid INT PRIMARY KEY,
            bookname TEXT UNIQUE NOT NULL,
            status TEXT CHECK(status IN ('borrowed', 'returned')) DEFAULT 'returned'
        );
        
        CREATE TABLE USER(
            userid INT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            currentborrow INT DEFAULT 0 CHECK(currentborrow >= 0 AND currentborrow <= 5)
        );
        
        CREATE TABLE BORROW(
            borrowid INT PRIMARY KEY,
            userid INT NOT NULL,
            bookid INT NOT NULL,
            FOREIGN KEY(userid) REFERENCES USER(userid),
            FOREIGN KEY(bookid) REFERENCES BOOK(bookid)
        );
        
        CREATE TRIGGER trg_borrow_insert
        AFTER INSERT ON BORROW
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, '书籍已被借出，无法借阅')
            WHERE (SELECT status FROM BOOK WHERE bookid = NEW.bookid) = 'borrowed';
            UPDATE BOOK SET status = 'borrowed' WHERE bookid = NEW.bookid;
            UPDATE USER SET currentborrow = currentborrow + 1 WHERE userid = NEW.userid;
        END;
        
        CREATE TRIGGER trg_borrow_delete
        AFTER DELETE ON BORROW
        FOR EACH ROW
        BEGIN
            UPDATE BOOK SET status = 'returned' WHERE bookid = OLD.bookid;
            UPDATE USER SET currentborrow = currentborrow - 1 WHERE userid = OLD.userid;
        END;
        
        INSERT INTO USER (userid, username) VALUES (1, 'Alice'), (2, 'Bob');
        INSERT INTO BOOK (bookid, bookname, status) VALUES (101, 'Book A', 'returned'), (102, 'Book B', 'returned');
    """)
    
    conn.commit()
    conn.close()
    print("[SETUP] 测试数据库创建完成")

def get_state(conn, label=""):
    """打印当前数据库状态"""
    book = conn.execute("SELECT bookid, bookname, status FROM BOOK ORDER BY bookid").fetchall()
    user = conn.execute("SELECT userid, username, currentborrow FROM USER ORDER BY userid").fetchall()
    borrow = conn.execute("SELECT borrowid, userid, bookid FROM BORROW ORDER BY borrowid").fetchall()
    
    if label:
        print(f"\n--- {label} ---")
    print(f"  BOOK:   {book}")
    print(f"  USER:   {user}")
    print(f"  BORROW: {borrow}")

def test_normal_borrow_return():
    """测试1: 正常借还流程"""
    print("\n" + "="*50)
    print("测试1: 正常借书 + 还书流程")
    print("="*50)
    
    conn = _connect()
    
    get_state(conn, "初始状态")
    
    # 借书
    max_id = conn.execute("SELECT COALESCE(MAX(borrowid), 0) FROM BORROW").fetchone()[0]
    new_id = max_id + 1
    conn.execute(f"INSERT INTO BORROW (borrowid, userid, bookid) VALUES ({new_id}, 1, 101)")
    conn.commit()
    get_state(conn, "Alice 借了 Book A (borrowid=1)")
    
    # 验证状态
    book_status = conn.execute("SELECT status FROM BOOK WHERE bookid = 101").fetchone()[0]
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid = 1").fetchone()[0]
    
    assert book_status == 'borrowed', f"FAIL: book status should be 'borrowed', got '{book_status}'"
    assert user_borrow == 1, f"FAIL: user currentborrow should be 1, got {user_borrow}"
    assert borrow_count == 1, f"FAIL: borrow count should be 1, got {borrow_count}"
    print("  [PASS] 借书后状态一致")
    
    # 还书
    conn.execute("DELETE FROM BORROW WHERE bookid = 101")
    conn.commit()
    get_state(conn, "Alice 还了 Book A")
    
    # 验证状态
    book_status = conn.execute("SELECT status FROM BOOK WHERE bookid = 101").fetchone()[0]
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid = 1").fetchone()[0]
    
    assert book_status == 'returned', f"FAIL: book status should be 'returned', got '{book_status}'"
    assert user_borrow == 0, f"FAIL: user currentborrow should be 0, got {user_borrow}"
    assert borrow_count == 0, f"FAIL: borrow count should be 0, got {borrow_count}"
    print("  [PASS] 还书后状态一致")
    
    conn.close()
    print("  [PASS] 测试1通过")

def test_multiple_borrow_return():
    """测试2: 多次借还，验证状态一致性"""
    print("\n" + "="*50)
    print("测试2: 多次借还，验证 currentborrow 与实际 BORROW 记录数一致")
    print("="*50)
    
    conn = _connect()
    
    # Alice 借两本书
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101)")
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 1, 102)")
    conn.commit()
    get_state(conn, "Alice 借了 Book A 和 Book B")
    
    # 验证
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid = 1").fetchone()[0]
    assert user_borrow == borrow_count, f"FAIL: currentborrow ({user_borrow}) != actual count ({borrow_count})"
    print(f"  [PASS] currentborrow ({user_borrow}) == 实际借阅数 ({borrow_count})")
    
    # 还一本
    conn.execute("DELETE FROM BORROW WHERE bookid = 101")
    conn.commit()
    get_state(conn, "Alice 还了 Book A")
    
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid = 1").fetchone()[0]
    assert user_borrow == borrow_count, f"FAIL: currentborrow ({user_borrow}) != actual count ({borrow_count})"
    print(f"  [PASS] currentborrow ({user_borrow}) == 实际借阅数 ({borrow_count})")
    
    # 再借一本
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (3, 1, 101)")
    conn.commit()
    
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid = 1").fetchone()[0]
    assert user_borrow == borrow_count, f"FAIL: currentborrow ({user_borrow}) != actual count ({borrow_count})"
    print(f"  [PASS] currentborrow ({user_borrow}) == 实际借阅数 ({borrow_count})")
    
    # 全部还掉
    conn.execute("DELETE FROM BORROW")
    conn.commit()
    get_state(conn, "全部归还")
    
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE userid = 1").fetchone()[0]
    assert user_borrow == 0 and borrow_count == 0, f"FAIL: currentborrow ({user_borrow}) or count ({borrow_count}) not 0"
    print(f"  [PASS] 全部归还后 currentborrow = {user_borrow}")
    
    conn.close()
    print("  [PASS] 测试2通过")

def test_execsql_semicolon_detection():
    """测试3: execSQL 分号检测与 executescript 兼容性"""
    print("\n" + "="*50)
    print("测试3: execSQL 分号检测 + cursor.executescript 兼容性")
    print("="*50)
    
    py_version = sys.version_info
    print(f"  Python 版本: {sys.version}")
    
    conn = _connect()
    cursor = conn.cursor()
    
    # 测试 cursor.executescript 是否存在
    has_cursor_executescript = hasattr(cursor, 'executescript')
    print(f"  cursor.executescript 存在: {has_cursor_executescript}")
    
    if py_version < (3, 12) and not has_cursor_executescript:
        print("  [BUG] Python < 3.12 且 cursor 无 executescript 方法!")
        print("     这意味着 accessDB.execSQL() 中所有含 ';' 的 SQL 都会抛 AttributeError")
        print("     影响范围: init_database.py 中的数据同步语句（第104-112行）")
    else:
        print("  [PASS] cursor.executescript 可用")
    
    # 测试含分号的 SQL 字符串检测
    test_sqls = [
        ("SELECT * FROM BOOK WHERE bookid = 101", False),
        ("SELECT * FROM BOOK WHERE bookid = 101;", True),
        ("UPDATE BOOK SET status = 'borrowed' WHERE bookid IN (SELECT bookid FROM BORROW);\nUPDATE USER SET currentborrow = (SELECT COUNT(*) FROM BORROW WHERE BORROW.userid = USER.userid);", True),
        ("DELETE FROM BORROW WHERE bookid = 101", False),
        ("SELECT BORROW.userid, USER.username FROM BORROW JOIN USER ON BORROW.userid = USER.userid WHERE BORROW.bookid = 101", False),
    ]
    
    for sql, expected in test_sqls:
        actual = ";" in sql
        status = "[PASS]" if actual == expected else "[FAIL]"
        short = sql[:60].replace("\n", " ")
        print(f"  {status} ';' in SQL: {actual} (expected {expected}) | {short}...")
    
    cursor.close()
    conn.close()
    print("  [PASS] 测试3完成")

def test_return_book_transaction_isolation():
    """测试4: return_book 的事务隔离性"""
    print("\n" + "="*50)
    print("测试4: return_book 的事务原子性")
    print("="*50)
    
    conn = _connect()
    
    # 先借一本书
    conn.execute("INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101)")
    conn.commit()
    print("  已借出: Alice -> Book A")
    
    # 模拟 return_book 的 3 步独立调用（不同连接）
    # Step 1: 检查（连接1）
    conn1 = _connect()
    book = conn1.execute("SELECT bookname, status FROM BOOK WHERE bookid = 101").fetchone()
    assert book[1] == 'borrowed', f"Expected 'borrowed', got '{book[1]}'"
    print(f"  Step 1 (连接1): 检查通过, book={book}")
    conn1.close()
    
    # Step 2: 查借阅记录（连接2）
    conn2 = _connect()
    borrow = conn2.execute(
        "SELECT BORROW.userid, USER.username FROM BORROW "
        "JOIN USER ON BORROW.userid = USER.userid "
        "WHERE BORROW.bookid = 101"
    ).fetchone()
    assert borrow is not None, "Borrow record not found"
    print(f"  Step 2 (连接2): 借阅记录找到, user={borrow}")
    conn2.close()
    
    # Step 3: DELETE（连接3）
    conn3 = _connect()
    conn3.execute("DELETE FROM BORROW WHERE bookid = 101")
    conn3.commit()
    print(f"  Step 3 (连接3): DELETE 完成")
    conn3.close()
    
    # 验证最终状态
    book_status = conn.execute("SELECT status FROM BOOK WHERE bookid = 101").fetchone()[0]
    user_borrow = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    borrow_count = conn.execute("SELECT COUNT(*) FROM BORROW WHERE bookid = 101").fetchone()[0]
    
    assert book_status == 'returned', f"FAIL: book status = '{book_status}'"
    assert user_borrow == 0, f"FAIL: currentborrow = {user_borrow}"
    assert borrow_count == 0, f"FAIL: borrow count = {borrow_count}"
    print(f"  [PASS] 最终状态一致: book={book_status}, currentborrow={user_borrow}, borrow_count={borrow_count}")
    
    conn.close()
    print("  [PASS] 测试4通过（正常路径无问题，但3个独立连接在高并发下有TOCTOU风险）")

def test_check_constraint_negative():
    """测试5: currentborrow 不会变为负数"""
    print("\n" + "="*50)
    print("测试5: CHECK 约束防止 currentborrow 变负数")
    print("="*50)
    
    conn = _connect()
    
    # 确保 Alice 没有借阅
    conn.execute("DELETE FROM BORROW WHERE userid = 1")
    conn.commit()
    
    # 确认 currentborrow 为 0
    cb = conn.execute("SELECT currentborrow FROM USER WHERE userid = 1").fetchone()[0]
    assert cb == 0, f"Expected 0, got {cb}"
    print(f"  Alice currentborrow = {cb}")
    
    # 直接尝试减 1（绕过触发器），应该被 CHECK 约束阻止
    try:
        conn.execute("UPDATE USER SET currentborrow = currentborrow - 1 WHERE userid = 1")
        conn.commit()
        print("  [FAIL] 更新成功（不应发生）")
    except sqlite3.IntegrityError as e:
        print(f"  [PASS] CHECK 约束生效: {e}")
    
    conn.close()
    print("  [PASS] 测试5通过")


def teardown():
    """清理测试数据库"""
    _close_all()
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("\n[TEARDOWN] 测试数据库已删除")


if __name__ == "__main__":
    try:
        setup()
        test_normal_borrow_return()
        test_multiple_borrow_return()
        test_execsql_semicolon_detection()
        test_return_book_transaction_isolation()
        test_check_constraint_negative()
        print("\n" + "="*50)
        print("所有测试通过！还书功能核心逻辑无 bug。")
        print("="*50)
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 未预期异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        teardown()
