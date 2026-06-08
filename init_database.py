from accessDB import accessDB, exampleDB
from pathlib import Path

dbPath = Path("./example.db")

# ============================================================================
# 可复用 SQL 常量 — 供 init_database 和 test_automated 共用
# ============================================================================

SCHEMA_SQL = """
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
"""

SMALL_SEED_SQL = """
    INSERT INTO USER (userid, username) VALUES
        (1, 'Alice'), (2, 'Bob'), (3, 'Charlie');
    INSERT INTO BOOK (bookid, bookname, status) VALUES
        (101, 'SQL 入门', 'returned'),
        (102, 'Python 进阶', 'returned'),
        (103, '算法导论', 'returned');
"""

SEED_SQL = """
    INSERT INTO USER (userid, username) VALUES
        (1, 'Alice'),
        (2, 'Bob'),
        (3, 'Charlie'),
        (4, 'Diana'),
        (5, 'Eve'),
        (6, 'Frank'),
        (7, 'Grace'),
        (8, 'Henry'),
        (9, 'Ivy'),
        (10, 'Jack');

    INSERT INTO BOOK (bookid, bookname, status) VALUES
        (101, 'The Great Gatsby', 'returned'),
        (102, '1984', 'returned'),
        (103, 'To Kill a Mockingbird', 'returned'),
        (104, 'Pride and Prejudice', 'returned'),
        (105, 'The Catcher in the Rye', 'returned'),
        (106, 'Moby Dick', 'returned'),
        (107, 'War and Peace', 'returned'),
        (108, 'Hamlet', 'returned'),
        (109, 'The Odyssey', 'returned'),
        (110, 'Brave New World', 'returned');

"""

VIEWS_SQL = """
    CREATE VIEW IF NOT EXISTS V_USER_BORROW AS
    SELECT BORROW.userid, USER.username, BOOK.bookid, BOOK.bookname
    FROM BORROW
    JOIN USER ON BORROW.userid = USER.userid
    JOIN BOOK ON BORROW.bookid = BOOK.bookid;

    CREATE VIEW IF NOT EXISTS V_BORROW_RANK AS
    SELECT username, currentborrow
    FROM USER
    ORDER BY currentborrow DESC;
"""


def init_to_db(db: accessDB, seed: str = SEED_SQL):
    """将结构和种子数据写入指定的 accessDB 实例（幂等建表）。"""
    db.execSQL_transaction(SCHEMA_SQL)
    db.execSQL_transaction(seed)
    db.execSQL_transaction(VIEWS_SQL)
    print("数据库初始化成功。")


def initial(db_path: Path | None = None):
    """生产环境初始化。若文件不存在则建库并填充数据。"""
    target = db_path or dbPath
    if not target.exists():
        db = accessDB(target)
        init_to_db(db)
    else:
        # 数据库已存在，仅确保视图存在
        db = accessDB(target)
        db.execSQL(VIEWS_SQL)


if __name__ == '__main__':
    initial()
