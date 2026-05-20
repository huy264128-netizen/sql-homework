# sql实现图书管理系统

### Table 1 (BOOK)
记录关于书的内容
|bookid|bookname|status|
|---|---|---|
|INT PRIMARY KEY|TEXT UNIQUE |'returned' or 'borrorwed'|
|书籍id|书籍名称|借书状态|

### Table 2 (USER)

|userid|username|currentborrow|
|---|---|---|
|INT PRIMARY KEY| TEXT | [0,5]|
|用户id | 用户的名字|用户现在借了几本书|
### Table3 (BORROW) 

|borrowid|userid|bookid|
|---|---|---|
|INT PRIMARY KEY| FOREIGN KEY|FOREIGN KEY|
|借贷记录id（主键）|用户id|书籍id|