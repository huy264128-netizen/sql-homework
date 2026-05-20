import sqlite3
from pathlib import Path
dbPath=Path("./example.db")
class accessDB:
    dbFile :Path = Path("example.db")
    def __init__(self,dbPath:Path):
        self.dbFile=dbPath
    def execSQL(self,sqlCmd:str)-> str:
        result=None
        with sqlite3.connect(self.dbFile) as db:
            cursor=db.cursor()
            cursor.execute(sqlCmd)
            result= cursor.fetchall()
            cursor.close()
        return result
exampleDB=accessDB(dbPath)