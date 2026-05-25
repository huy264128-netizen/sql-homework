import sqlite3
from pathlib import Path
dbPath=Path("./example.db")
class accessDB:
    dbFile :Path = Path("example.db")
    def __init__(self,dbPath:Path):
        self.dbFile=dbPath
    def execSQL(self, sqlCmd: str) -> list[tuple] | None:
        """执行 SQL 语句。支持多条语句（用 ; 分隔），多语句时返回 None。"""
        result = None
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            cursor = db.cursor()
            # 多语句使用 executescript；单语句使用 execute 以便 fetchall
            if ";" in sqlCmd:
                cursor.executescript(sqlCmd)
                result = None
            else:
                cursor.execute(sqlCmd)
                result = cursor.fetchall()
            cursor.close()
        return result

    def execSQL_transaction(self, sqlCmd: str) -> None:
        """在事务中执行多条 SQL 语句（用 ; 分隔），失败自动回滚。"""
        with sqlite3.connect(self.dbFile) as db:
            db.execute("PRAGMA foreign_keys = ON")
            cursor = db.cursor()
            try:
                cursor.execute("BEGIN")
                for stmt in sqlCmd.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cursor.execute(stmt)
                cursor.execute("COMMIT")
            except Exception:
                cursor.execute("ROLLBACK")
                raise
            finally:
                cursor.close()

    # -----------------------------------------------------------------------
    # 应用层存储过程
    # -----------------------------------------------------------------------

    def borrow_book(self, userid: int, bookid: int) -> tuple[int, str, str]:
        """
        借书存储过程。

        校验用户/书是否存在、是否可借，插入 BORROW 记录。
        触发器 trg_borrow_insert 自动更新 BOOK/USER 状态。

        返回: (borrowid, username, bookname)
        异常: ValueError - 业务规则不满足；sqlite3.Error - 数据库约束违反
        """
        # 1. 检查用户
        user = self.execSQL(
            f"SELECT username, currentborrow FROM USER WHERE userid = {userid}"
        )
        if not user:
            raise ValueError(f"用户 {userid} 不存在")
        username, current_borrow = user[0]

        # 2. 检查借书上限
        if current_borrow >= 5:
            raise ValueError(f"用户 '{username}' 已借满 5 本书，无法再借")

        # 3. 检查书籍
        book = self.execSQL(
            f"SELECT bookname, status FROM BOOK WHERE bookid = {bookid}"
        )
        if not book:
            raise ValueError(f"书籍 {bookid} 不存在")
        bookname, status = book[0]

        # 4. 检查是否已被借出
        if status == "borrowed":
            raise ValueError(f"书籍 '{bookname}' 已被借出，暂时无法借阅")

        # 5. 生成 borrowid
        max_id = self.execSQL("SELECT COALESCE(MAX(borrowid), 0) FROM BORROW")
        if not max_id:
            raise RuntimeError("查询 borrowid 失败")
        new_id = max_id[0][0] + 1

        # 6. 插入借阅记录（触发器自动更新 BOOK/USER）
        self.execSQL(
            f"INSERT INTO BORROW (borrowid, userid, bookid) "
            f"VALUES ({new_id}, {userid}, {bookid})"
        )
        return (new_id, username, bookname)

    def return_book(self, bookid: int) -> tuple[str, str]:
        """
        还书存储过程。

        校验书是否存在且已借出，删除 BORROW 记录。
        触发器 trg_borrow_delete 自动恢复 BOOK/USER 状态。

        返回: (username, bookname)
        异常: ValueError - 业务规则不满足；sqlite3.Error - 数据库异常
        """
        # 1. 检查书籍
        book = self.execSQL(
            f"SELECT bookname, status FROM BOOK WHERE bookid = {bookid}"
        )
        if not book:
            raise ValueError(f"书籍 {bookid} 不存在")
        bookname, status = book[0]

        # 2. 检查是否已被借出
        if status != "borrowed":
            raise ValueError(f"书籍 '{bookname}' 未被借出，无需归还")

        # 3. 查询借阅记录获取 userid
        borrow = self.execSQL(
            f"SELECT BORROW.userid, USER.username FROM BORROW "
            f"JOIN USER ON BORROW.userid = USER.userid "
            f"WHERE BORROW.bookid = {bookid}"
        )
        if not borrow:
            raise ValueError(f"未找到书籍 {bookid} 的借阅记录")
        userid, username = borrow[0]

        # 4. 删除借阅记录（触发器自动恢复 BOOK/USER）
        self.execSQL(f"DELETE FROM BORROW WHERE bookid = {bookid}")
        return (username, bookname)

exampleDB = accessDB(dbPath)