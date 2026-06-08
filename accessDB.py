import sqlite3
from pathlib import Path
dbPath=Path("./example.db")
class accessDB:
    dbFile :Path = Path("example.db")
    def __init__(self,dbPath:Path):
        self.dbFile=dbPath
    def execSQL(self, sqlCmd: str) -> list[tuple] | None:
        """执行 SQL 语句。支持多条语句（用 ; 分隔），多语句时返回 None。"""
        print(f"[SQL] {sqlCmd}")
        result = None
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            # 多语句使用 db.executescript（连接级别，正确处理触发器体内的 ;）
            if ";" in sqlCmd:
                db.executescript(sqlCmd)
                result = None
            else:
                cursor = db.cursor()
                cursor.execute(sqlCmd)
                result = cursor.fetchall()
                cursor.close()
        return result

    def execSQL_transaction(self, sqlCmd: str) -> None:
        """在事务中执行多条 SQL 语句，失败自动回滚。

        使用 executescript 而非 split(";") 逐条执行，避免触发器/存储过程
        体内的 ; 被错误拆分（如 CREATE TRIGGER ... BEGIN ... END;）。
        """
        print(f"[SQL] {sqlCmd}")
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            # 用 SQL 级别的 BEGIN/COMMIT 包裹，确保原子性
            full_sql = "BEGIN;\n" + sqlCmd + "\nCOMMIT;"
            try:
                db.executescript(full_sql)
            except Exception:
                # 异常时显式 ROLLBACK，防止残留未关闭的事务
                try:
                    db.executescript("ROLLBACK;")
                except Exception:
                    pass
                raise

    # -----------------------------------------------------------------------
    # 应用层存储过程（单事务保证原子性）
    # -----------------------------------------------------------------------

    def borrow_book(self, userid: int, bookid: int) -> tuple[int, str, str]:
        """
        借书存储过程 —— 所有检查 + INSERT 在同一事务中完成，消除 TOCTOU 竞态。

        触发器 trg_borrow_insert 自动更新 BOOK/USER 状态。

        返回: (borrowid, username, bookname)
        异常: ValueError - 业务规则不满足；sqlite3.Error - 数据库约束违反
        """
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            cur = db.cursor()
            try:
                cur.execute("BEGIN")

                # 1. 检查用户是否存在 + 借书上限（事务内，防止并发修改）
                cur.execute(
                    f"SELECT username, currentborrow FROM USER WHERE userid = {userid}"
                )
                user = cur.fetchone()
                if not user:
                    raise ValueError(f"用户 {userid} 不存在")
                username, current_borrow = user
                if current_borrow >= 5:
                    raise ValueError(f"用户 '{username}' 已借满 5 本书，无法再借")

                # 2. 检查书籍是否存在 + 是否已被借出（事务内）
                cur.execute(
                    f"SELECT bookname, status FROM BOOK WHERE bookid = {bookid}"
                )
                book = cur.fetchone()
                if not book:
                    raise ValueError(f"书籍 {bookid} 不存在")
                bookname, status = book
                if status == "borrowed":
                    raise ValueError(f"书籍 '{bookname}' 已被借出，暂时无法借阅")

                # 3. 生成 borrowid（事务内，保证 MAX 读与 INSERT 原子）
                cur.execute("SELECT COALESCE(MAX(borrowid), 0) FROM BORROW")
                new_id = cur.fetchone()[0] + 1

                # 4. 插入借阅记录（触发器 trg_borrow_insert 自动更新 BOOK/USER）
                cur.execute(
                    f"INSERT INTO BORROW (borrowid, userid, bookid) "
                    f"VALUES ({new_id}, {userid}, {bookid})"
                )
                cur.execute("COMMIT")
                print(f"[SQL] borrow_book OK: user='{username}' -> '{bookname}' (borrowid={new_id})")
                return (new_id, username, bookname)
            except Exception:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    def return_book(self, bookid: int) -> tuple[str, str]:
        """
        还书存储过程 —— 所有检查 + DELETE 在同一事务中完成，消除 TOCTOU 竞态。

        触发器 trg_borrow_delete 自动恢复 BOOK/USER 状态。

        返回: (username, bookname)
        异常: ValueError - 业务规则不满足；sqlite3.Error - 数据库异常
        """
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            cur = db.cursor()
            try:
                cur.execute("BEGIN")

                # 1. 检查书籍是否存在 + 是否处于借出状态（事务内）
                cur.execute(
                    f"SELECT bookname, status FROM BOOK WHERE bookid = {bookid}"
                )
                book = cur.fetchone()
                if not book:
                    raise ValueError(f"书籍 {bookid} 不存在")
                bookname, status = book
                if status != "borrowed":
                    raise ValueError(f"书籍 '{bookname}' 未被借出，无需归还")

                # 2. 查询借阅记录获取借阅人信息（事务内）
                cur.execute(
                    f"SELECT BORROW.userid, USER.username FROM BORROW "
                    f"JOIN USER ON BORROW.userid = USER.userid "
                    f"WHERE BORROW.bookid = {bookid}"
                )
                borrow = cur.fetchone()
                if not borrow:
                    raise ValueError(f"未找到书籍 {bookid} 的借阅记录")
                userid, username = borrow

                # 3. 删除借阅记录（触发器 trg_borrow_delete 自动恢复 BOOK/USER）
                cur.execute(f"DELETE FROM BORROW WHERE bookid = {bookid}")
                cur.execute("COMMIT")
                print(f"[SQL] return_book OK: '{bookname}' returned by '{username}'")
                return (username, bookname)
            except Exception:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    def add_user(self, username: str) -> int:
        """
        添加新用户存储过程 —— 冲突检查 + INSERT 在同一事务中完成。

        返回: userid
        异常: ValueError - 用户名已存在；sqlite3.Error - 数据库异常
        """
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            cur = db.cursor()
            try:
                cur.execute("BEGIN")

                # 1. 检查用户名冲突（事务内）
                cur.execute(
                    f"SELECT userid FROM USER WHERE username = '{username}'"
                )
                if cur.fetchone():
                    raise ValueError(f"用户名 '{username}' 已存在")

                # 2. 生成 userid（事务内）
                cur.execute("SELECT COALESCE(MAX(userid), 0) FROM USER")
                new_id = cur.fetchone()[0] + 1

                # 3. 插入新用户
                cur.execute(
                    f"INSERT INTO USER (userid, username, currentborrow) "
                    f"VALUES ({new_id}, '{username}', 0)"
                )
                cur.execute("COMMIT")
                print(f"[SQL] add_user OK: username='{username}', userid={new_id}")
                return new_id
            except Exception:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    def add_book(self, bookname: str) -> int:
        """
        添加新书籍存储过程 —— 冲突检查 + INSERT 在同一事务中完成。

        返回: bookid
        异常: ValueError - 书名已存在；sqlite3.Error - 数据库异常
        """
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            cur = db.cursor()
            try:
                cur.execute("BEGIN")

                # 1. 检查书名冲突（事务内）
                cur.execute(
                    f"SELECT bookid FROM BOOK WHERE bookname = '{bookname}'"
                )
                if cur.fetchone():
                    raise ValueError(f"书名 '{bookname}' 已存在")

                # 2. 生成 bookid（事务内）
                cur.execute("SELECT COALESCE(MAX(bookid), 0) FROM BOOK")
                new_id = cur.fetchone()[0] + 1

                # 3. 插入新书籍
                cur.execute(
                    f"INSERT INTO BOOK (bookid, bookname, status) "
                    f"VALUES ({new_id}, '{bookname}', 'returned')"
                )
                cur.execute("COMMIT")
                print(f"[SQL] add_book OK: bookname='{bookname}', bookid={new_id}")
                return new_id
            except Exception:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    def get_user_id(self, username: str) -> int:
        """根据用户名查找 userid，找不到抛出 ValueError。"""
        row = self.execSQL(
            f"SELECT userid FROM USER WHERE username = '{username}'"
        )
        if not row:
            raise ValueError(f"用户 '{username}' 不存在")
        return row[0][0]

    def get_book_id(self, bookname: str) -> int:
        """根据书名查找 bookid，找不到抛出 ValueError。"""
        row = self.execSQL(
            f"SELECT bookid FROM BOOK WHERE bookname = '{bookname}'"
        )
        if not row:
            raise ValueError(f"书籍 '{bookname}' 不存在")
        return row[0][0]

exampleDB = accessDB(dbPath)
