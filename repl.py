import init_database
from accessDB import exampleDB
def main():
    init_database.initial()
    inputCmd =input()
    while inputCmd!="exit":
        print(exampleDB.execSQL(inputCmd))
        inputCmd=input()
if __name__=='__main__':
    main()