# 图书管理系统 — 自动化测试报告

> **测试程序**: `test_automated.py`  
> **测试日期**: 2026-06-08
> **测试结果**: ✅ **40/40 全部通过**

---

## 测试覆盖总览

| 测试部分 | 测试对象 | 用例数 | 结果 |
|----------|----------|--------|------|
| 第一部分 | 表结构与约束 | 9 | ✅ |
| 第二部分 | 触发器 `trg_borrow_insert` | 5 | ✅ |
| 第三部分 | 触发器 `trg_borrow_delete` | 3 | ✅ |
| 第四部分 | 应用层存储过程（事务原子性） | 10 | ✅ |
| 第五部分 | 视图 `V_USER_BORROW` / `V_BORROW_RANK` | 3 | ✅ |
| 第六部分 | REPL 快捷指令集成测试 | 10 | ✅ |
| **合计** | | **40** | **✅** |

---

## 第一部分：表结构与约束（9 项）

### 测试对象
`BOOK`、`USER`、`BORROW` 三张核心表的 DDL 约束：
- `PRIMARY KEY` — 主键唯一性
- `UNIQUE` — 用户名/书名不可重复
- `FOREIGN KEY` — 参照完整性
- `CHECK` — 状态值和借阅数量的合法性校验

### 测试内容

| 编号 | 测试项 | 操作 | 预期行为 | 结果 |
|------|--------|------|----------|------|
| 1.1 | PRIMARY KEY 唯一性 | `INSERT INTO USER (userid, username) VALUES (1, 'Duplicate')` — userid=1 已存在 | 抛出 `IntegrityError` | ✅ |
| 1.2 | UNIQUE — username | `INSERT INTO USER (userid, username) VALUES (4, 'Alice')` — username 重复 | 抛出 `IntegrityError` | ✅ |
| 1.3 | UNIQUE — bookname | `INSERT INTO BOOK (bookid, bookname) VALUES (201, 'SQL 入门')` — 书名重复 | 抛出 `IntegrityError` | ✅ |
| 1.4 | FOREIGN KEY — userid | `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 999, 101)` — 用户不存在 | 抛出 `IntegrityError` | ✅ |
| 1.5 | FOREIGN KEY — bookid | `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 999)` — 书籍不存在 | 抛出 `IntegrityError` | ✅ |
| 1.6 | CHECK — BOOK.status | `INSERT INTO BOOK (bookid, bookname, status) VALUES (201, 'Test', 'invalid')` — 非法状态值 | 抛出 `IntegrityError` | ✅ |
| 1.7 | CHECK — 借阅上限 | `UPDATE USER SET currentborrow = 6 WHERE userid = 1` — 超出上限 5 | 抛出 `IntegrityError` | ✅ |
| 1.8 | CHECK — 负数 | `UPDATE USER SET currentborrow = -1 WHERE userid = 1` — 负数 | 抛出 `IntegrityError` | ✅ |
| 1.9 | 正常插入 | `INSERT INTO USER (userid, username) VALUES (4, 'Diana');`<br>`INSERT INTO BOOK (bookid, bookname) VALUES (201, '新书');`<br>`SELECT username FROM USER WHERE userid=4;`<br>`SELECT bookname FROM BOOK WHERE bookid=201;` | 数据正确写入，分别返回 `'Diana'` 和 `'新书'` | ✅ |

---

## 第二部分：触发器 `trg_borrow_insert`（5 项）

### 测试对象
`AFTER INSERT ON BORROW` 触发器，负责：
1. **RAISE ABORT** — 阻止已借出书籍被再次借阅
2. **自动同步** — 插入借阅记录后自动更新 `BOOK.status` 和 `USER.currentborrow`

### 测试内容

| 编号 | 测试项 | 操作 | 预期行为 | 结果 |
|------|--------|------|----------|------|
| 2.1 | 正常借书 | `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101)` | `BOOK.status='borrowed'`，`USER.currentborrow=1` | ✅ |
| 2.2 | 重复借同一本书 | 再 `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 2, 101)` | RAISE ABORT，抛出异常 `"书籍已被借出，无法借阅"` | ✅ |
| 2.3 | 多用户借不同书 | `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101);`<br>`INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 2, 102);`<br>`INSERT INTO BORROW (borrowid, userid, bookid) VALUES (3, 3, 103);` | 各自 `currentborrow` 分别为 1，互不干扰 | ✅ |
| 2.4 | 同一用户借多书 | `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101);`<br>`INSERT INTO BORROW (borrowid, userid, bookid) VALUES (2, 1, 102);` | `currentborrow=2`，2本书 `status='borrowed'` | ✅ |
| 2.5 | 借书达上限 | 先插入5条借阅：<br>`INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1,1,101),(2,1,102),(3,1,103),(4,1,104),(5,1,105);`<br>再尝试 `INSERT INTO BORROW (borrowid, userid, bookid) VALUES (6, 1, 106);` | 第6本被 CHECK 约束或触发器阻止 | ✅ |

---

## 第三部分：触发器 `trg_borrow_delete`（3 项）

### 测试对象
`AFTER DELETE ON BORROW` 触发器，负责还书时自动恢复状态：
- `BOOK.status` → `'returned'`
- `USER.currentborrow` → 减 1

### 测试内容

| 编号 | 测试项 | 操作 | 预期行为 | 结果 |
|------|--------|------|----------|------|
| 3.1 | 正常还书 | 前置：`INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101), (2, 1, 102), (3, 2, 103);`<br>`DELETE FROM BORROW WHERE bookid=101` | `BOOK.status='returned'`，Alice 的 `currentborrow` 从2降为1 | ✅ |
| 3.2 | 还清所有书 | 再 `DELETE FROM BORROW WHERE bookid=102` | Alice 的 `currentborrow=0` | ✅ |
| 3.3 | 还另一用户的书 | `DELETE FROM BORROW WHERE bookid=103`（Bob 借的） | Bob 的 `currentborrow` 归0 | ✅ |

---

## 第四部分：应用层存储过程（事务原子性）（10 项）

### 测试对象
[`accessDB.py`](accessDB.py) 中的四个"存储过程"方法，每个都在单事务（`BEGIN/COMMIT/ROLLBACK`）中执行：

| 方法 | 功能 | 文件位置 |
|------|------|----------|
| `borrow_book(userid, bookid)` | 借书 | [accessDB.py:48](accessDB.py:48) |
| `return_book(bookid)` | 还书 | [accessDB.py:103](accessDB.py:103) |
| `add_user(username)` | 添加用户 | [accessDB.py:151](accessDB.py:151) |
| `add_book(bookname)` | 添加书籍 | [accessDB.py:189](accessDB.py:189) |

**事务设计**：所有检查（用户是否存在、书是否已借出、是否重复）和数据库写入在同一个 `BEGIN/COMMIT` 中完成，杜绝 TOCTOU 竞态条件。

### 测试内容

| 编号 | 测试项 | 操作 | 预期行为 | 结果 |
|------|--------|------|----------|------|
| 4.1 | borrow_book 正常 | `db.borrow_book(1, 101)` | 返回 `(borrowid=1, 'Alice', 'SQL 入门')` | ✅ |
| 4.2 | borrow_book 书已借 | 再次 `db.borrow_book(2, 101)` | 抛出 `ValueError: 书籍 'SQL 入门' 已被借出` | ✅ |
| 4.3 | borrow_book 用户不存在 | `db.borrow_book(999, 102)` | 抛出 `ValueError` | ✅ |
| 4.4 | return_book 正常 | `db.return_book(101)` | 返回 `('Alice', 'SQL 入门')`，状态恢复为 `returned` | ✅ |
| 4.5 | return_book 书未借 | 再次 `db.return_book(101)` | 抛出 `ValueError` | ✅ |
| 4.6 | add_user 正常 | `db.add_user('Diana')` | 返回新 userid=4，表中可查到 | ✅ |
| 4.7 | add_user 用户重复 | `db.add_user('Alice')` | 抛出 `ValueError` | ✅ |
| 4.8 | add_book 正常 | `db.add_book('新书推荐')` | 返回新 bookid=104，表中可查到 | ✅ |
| 4.9 | add_book 书名重复 | `db.add_book('SQL 入门')` | 抛出 `ValueError` | ✅ |
| 4.10 | 事务原子性 | 先手动插入借阅使102被借（`INSERT INTO BORROW VALUES (10, 1, 102)`），然后 `db.borrow_book(2, 102)` 预期失败 | Bob 的 `currentborrow` 保持为0，未被污染（ROLLBACK 生效） | ✅ |

---

## 第五部分：视图（3 项）

### 测试对象
- **`V_USER_BORROW`** — 用户借阅明细（JOIN 三表）
- **`V_BORROW_RANK`** — 用户借阅排行（按 `currentborrow` 降序）

### 测试内容

| 编号 | 测试项 | 操作 | 预期行为 | 结果 |
|------|--------|------|----------|------|
| 5.1 | V_USER_BORROW | 前置：`INSERT INTO BORROW (borrowid, userid, bookid) VALUES (1, 1, 101), (2, 1, 102), (3, 2, 103);`<br>`SELECT username, bookid, bookname FROM V_USER_BORROW WHERE userid=1;` | 返回 2 条记录，JOIN 出 username 和 bookname | ✅ |
| 5.2 | V_BORROW_RANK | 前置（同上 insert），查询 `SELECT * FROM V_BORROW_RANK;` | Alice(2本) 排第一，Bob(1本) 第二，Charlie(0本) 第三 | ✅ |
| 5.3 | 视图实时更新 | `DELETE FROM BORROW WHERE bookid=102;`<br>`SELECT * FROM V_BORROW_RANK WHERE username='Alice';` | V_BORROW_RANK 中 Alice 从2降为1 | ✅ |

---

## 第六部分：REPL 快捷指令集成测试（10 项）

### 测试对象
[`repl.py`](repl.py) 中所有注册的快捷指令，通过 `_command_registry` 直接调用命令处理函数，验证它们与 [`accessDB`](accessDB.py) 的集成是否正常。

### 测试内容

| 编号 | 测试项 | 命令 | 预期行为 | 结果 |
|------|--------|------|----------|------|
| 6.1 | `.borrow` ID方式 | `.borrow 1 101` | 借书成功，Alice 借到 SQL 入门 | ✅ |
| 6.2 | `.borrow` 名称方式 | `.borrow Bob 'Python 进阶'` | Bob 通过名称借书成功 | ✅ |
| 6.3 | `.borrow` 重复借 | `.borrow 3 101`（已被借） | 提示借书失败 | ✅ |
| 6.4 | `.return` ID方式 | `.return 101` | 还书成功，Alice 归还 SQL 入门 | ✅ |
| 6.5 | `.return` 书名方式 | `.return 'Python 进阶'` | Bob 通过书名还书成功 | ✅ |
| 6.6 | `.adduser` | `.adduser 张三` | 用户添加成功，返回 userid | ✅ |
| 6.7 | `.addbook` | `.addbook 三体` | 书籍添加成功，返回 bookid | ✅ |
| 6.8 | `.listborrow` | `.listborrow Alice` | 查询 Alice 的借阅记录（无借阅时提示"没有"） | ✅ |
| 6.9 | `.rank` | `.rank` | 显示借阅排行 | ✅ |
| 6.10 | `.tables` | `.tables` | 列出 BOOK、USER、BORROW 三张表 | ✅ |

---

## 重构说明

### `init_database.py` 重构

将原本散落在 `initial()` 函数中的 SQL 字符串提取为**模块级常量**，使测试程序可直接复用：

| 常量 | 内容 |
|------|------|
| `SCHEMA_SQL` | CREATE TABLE + TRIGGER（不含数据） |
| `SMALL_SEED_SQL` | 3用户 3书籍（轻量测试用） |
| `SEED_SQL` | 10用户 10书籍（完整生产数据） |
| `VIEWS_SQL` | CREATE VIEW 语句 |

新增 `init_to_db(db, seed)` 函数，接受任意 `accessDB` 实例和种子数据，测试代码可直接调用。

---

## 运行方式

```bash
# 运行全部测试（需要先确保 init_database.py 在同一目录）
python test_automated.py

# 退出码：0=全部通过，1=存在失败
```

---

## 测试架构说明

- **约束/触发器/视图测试**（1-3、5）：使用 SQLite `:memory:` 数据库，完全隔离，可并行运行
- **存储过程测试**（4）：使用文件数据库 `_test_sp.db`，因为需要 `accessDB` 类的完整事务逻辑
- **REPL 集成测试**（6）：使用文件数据库 `_test_repl.db`，通过替换 `repl.exampleDB` 指向测试库
- 测试结束后自动清理临时文件
