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
                           totalcount INT NOT NULL,
                           currentcount INT NOT NULL )""")
            cursor.execute("""CREATE TABLE USER(
                           userid INT PRIMARY KEY,
                           username TEXT UNIQUE,
                           currentborrow INT NOT NULL)""")
            cursor.execute("""CREATE TABLE BORROW(
                           borrowid INT PRIMARY KEY,
                           userid INT,
                           bookid INT)""")
if __name__=='__main__':
    initial()
        
