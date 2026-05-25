from accessDB import exampleDB
from pathlib import Path
dbPath=Path("./example.db")
def initial():
    if not dbPath.exists():
        exampleDB.execSQL("""
            CREATE TABLE BOOK(
                bookid INT PRIMARY KEY,
                bookname TEXT UNIQUE NOT NULL,
                status TEXT CHECK(status IN ('borrowed', 'returned')) DEFAULT 'returned'
            )""")
        
        exampleDB.execSQL("""
            CREATE TABLE USER(
                userid INT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                currentborrow INT DEFAULT 0 CHECK(currentborrow >= 0 AND currentborrow <= 5)
            )""")
        
        exampleDB.execSQL("""
            CREATE TABLE BORROW(
                borrowid INT PRIMARY KEY,
                userid INT NOT NULL,
                bookid INT NOT NULL,
                FOREIGN KEY(userid) REFERENCES USER(userid),
                FOREIGN KEY(bookid) REFERENCES BOOK(bookid)
            )""")

        # 触发器：插入借阅记录时自动更新 BOOK 状态和 USER 借阅数
        exampleDB.execSQL("""
            CREATE TRIGGER trg_borrow_insert
            AFTER INSERT ON BORROW
            FOR EACH ROW
            BEGIN
                -- 检查书籍是否已被借出（是则阻止插入并回滚）
                SELECT RAISE(ABORT, '书籍已被借出，无法借阅')
                WHERE (SELECT status FROM BOOK WHERE bookid = NEW.bookid) = 'borrowed';

                -- 更新书籍状态
                UPDATE BOOK SET status = 'borrowed' WHERE bookid = NEW.bookid;

                -- 更新用户借阅数（CHECK 约束 currentborrow<=5 会在超限时自动阻止）
                UPDATE USER SET currentborrow = currentborrow + 1 WHERE userid = NEW.userid;
            END;
        """)

        #数据插入
        # 插入10个用户
        exampleDB.execSQL("""
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
        """)

        # 插入10本书
        exampleDB.execSQL("""
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
        """)

        # 插入10条借阅记录
        exampleDB.execSQL("""
            INSERT INTO BORROW (borrowid, userid, bookid) VALUES
            (1, 1, 101),
            (2, 1, 102),
            (3, 2, 103),
            (4, 2, 104),
            (5, 3, 105),
            (6, 3, 106),
            (7, 4, 107),
            (8, 5, 108),
            (9, 6, 109),
            (10, 7, 110);
        """)

        # 同步更新书籍状态与用户当前借阅数
        exampleDB.execSQL("""
            UPDATE BOOK SET status = 'borrowed'
            WHERE bookid IN (SELECT bookid FROM BORROW);

            UPDATE USER SET currentborrow = (
                SELECT COUNT(*) FROM BORROW WHERE BORROW.userid = USER.userid
            );
        """)
     
        print("数据库初始化成功。")

    # 视图：用户借阅明细（每次启动都确保存在，幂等 CREATE IF NOT EXISTS）
    exampleDB.execSQL("""
        CREATE VIEW IF NOT EXISTS V_USER_BORROW AS
        SELECT BORROW.userid, USER.username, BOOK.bookid, BOOK.bookname
        FROM BORROW
        JOIN USER ON BORROW.userid = USER.userid
        JOIN BOOK ON BORROW.bookid = BOOK.bookid
    """)

if __name__ == '__main__':
    initial()
        
