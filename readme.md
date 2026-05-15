# sql作业...

只是一个简单的普通的SQL作业 基于sqlite3库

## 题材

图书管理系统 

### Table 1 (Book)
记录关于书的内容
|Book id | Book Name | Status|
|---|---|---|
|INT PRIMARY KEY|TEXT UNIQUE |'returned' or 'borrorwed'|
|书籍id|书籍名称|借书状态|

### Table 2 (User)

|User id | User Name | Current Borrow |
|---|---|---|
|INT PRIMARY KEY| TEXT | [0,5]|
|用户id | 用户的名字|用户现在借了几本书|
### Table3 (Borrow) 

|Borrow id|User id| Book id|
|---|---|---|
|INT PRIMARY KEY| FOREIGN KEY|FOREIGN KEY|
|借贷记录id（主键）|用户id|书籍id|