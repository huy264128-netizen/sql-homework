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
exampleDB=accessDB(dbPath)