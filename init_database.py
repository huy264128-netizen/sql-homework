from accessDB import exampleDB
from pathlib import Path
dbPath=Path("./example.db")
def initial():
    if not dbPath.exists():
        exampleDB.execSQL("""
                           CREATE TABLE BOOK(
                           bookid INT PRIMARY KEY,
                           bookname TEXT UNIQUE,
                           status TEXT CHECK(STATUS IN('borrowed','returned') ) )""")
        exampleDB.execSQL("""CREATE TABLE USER(
                           userid INT PRIMARY KEY,
                           username TEXT UNIQUE,
                           currentborrow INT CHECK(currentborrow>=0 AND currentborrow<=5))""")
        exampleDB.execSQL("""CREATE TABLE BORROW(
                           borrowid INT PRIMARY KEY,
                           userid INT,
                           bookid INT)""")
if __name__=='__main__':
    initial()
        
