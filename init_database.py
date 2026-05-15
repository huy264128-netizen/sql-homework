import sqlite3
from pathlib import Path
dbPath=Path("./example.db")
def initial():
    if not dbPath.exists():
        with sqlite3.connect(dbPath) as db:
            cursor=db.cursor()
            cursor.execute("""
                           CREATE TABLE BOOK(
                           bookid INT PRIMARY KEY,
                           bookname TEXT UNIQUE,
                           status IN ('borrowed','returned') )""")
            cursor.execute("""CREATE TABLE USER(
                           userid INT PRIMARY KEY,
                           username TEXT UNIQUE,
                           currentborrow INT CHECK(currentborrow>=0 AND currentborrow<=5))""")
            cursor.execute("""CREATE TABLE BORROW(
                           borrowid INT PRIMARY KEY,
                           userid INT,
                           bookid INT)""")
if __name__=='__main__':
    initial()
        
