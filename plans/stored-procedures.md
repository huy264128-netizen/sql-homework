# 应用层存储过程设计方案

## 一、设计思路

SQLite 不支持原生 `CREATE PROCEDURE`，因此在 [`accessDB`](accessDB.py:4) 类中封装 Python 方法作为「应用层存储过程」。借书/还书的核心状态更新继续由触发器自动完成，Python 端只负责：

- 参数校验
- 业务规则检查（用户是否存在、书是否可借等）
- 执行 INSERT / DELETE（触发触发器自动更新 BOOK/USER 状态）

```
用户输入 .borrow 1 109
  └→ cmd_borrow() 参数校验
       └→ exampleDB.borrow_book(1, 109)   ← 应用层存储过程
            ├─ 检查 USER 存在 + 借书上限
            ├─ 检查 BOOK 存在 + 未被借出
            ├─ 生成 borrowid
            └─ INSERT INTO BORROW    ← 触发器自动：
                  ├─ UPDATE BOOK SET status='borrowed'
                  └─ UPDATE USER SET currentborrow += 1
```

## 二、新增 DELETE 触发器

还书 = 删除 BORROW 记录。需要一个 `AFTER DELETE` 触发器自动恢复 BOOK/USER 状态。

```sql
CREATE TRIGGER IF NOT EXISTS trg_borrow_delete
AFTER DELETE ON BORROW
FOR EACH ROW
BEGIN
    UPDATE BOOK SET status = 'returned' WHERE bookid = OLD.bookid;
    UPDATE USER SET currentborrow = currentborrow - 1 WHERE userid = OLD.userid;
END;
```

放在 [`init_database.py`](init_database.py:1) 的 `if` 块内（和 INSERT 触发器同级）。

## 三、accessDB 新增方法

### 3.1 `borrow_book(userid, bookid) -> str`

| 步骤 | 操作 | 异常 |
|------|------|------|
| 1 | 查询 USER 是否存在 + currentborrow | 用户不存在 |
| 2 | 检查 currentborrow < 5 | 已达上限 |
| 3 | 查询 BOOK 是否存在 + status | 书不存在 |
| 4 | 检查 status != 'borrowed' | 已被借出 |
| 5 | `SELECT MAX(borrowid)` 生成新 ID | — |
| 6 | `INSERT INTO BORROW` | 外键/触发器异常 |

返回：成功时返回 `(borrowid, username, bookname)` 三元组；失败抛异常。

### 3.2 `return_book(bookid) -> str`

| 步骤 | 操作 | 异常 |
|------|------|------|
| 1 | 查询 BOOK 是否存在 + status | 书不存在 |
| 2 | 检查 status == 'borrowed' | 书未被借出 |
| 3 | 查询 BORROW 记录获取 userid | 无借阅记录 |
| 4 | `DELETE FROM BORROW WHERE bookid = ?` | 触发器异常 |

返回：成功时返回 `(username, bookname)` 二元组；失败抛异常。

## 四、repl.py 改造

### `.borrow` 简化

```python
@register_command("borrow", ...)
def cmd_borrow(args):
    # 参数校验（不变）
    userid, bookid = validate(args)
    try:
        bid, username, bookname = exampleDB.borrow_book(userid, bookid)
        return f"借书成功! 用户 '{username}' 借阅了 '{bookname}'（借阅记录ID: {bid}）"
    except Exception as e:
        return f"借书失败: {e}"
```

### `.return` 新增

```python
@register_command("return", help_text="还书 (.return [书id])", aliases=["rt"])
def cmd_return(args):
    args = args.strip()
    if not args or not args.isdigit():
        return "用法: .return [书id]\n示例: .return 109"
    bookid = int(args)
    try:
        username, bookname = exampleDB.return_book(bookid)
        return f"还书成功! 用户 '{username}' 归还了 '{bookname}'"
    except Exception as e:
        return f"还书失败: {e}"
```

## 五、受影响文件清单

| 文件 | 改动 |
|------|------|
| [`init_database.py`](init_database.py:44) | 在 `trg_borrow_insert` 后追加 `CREATE TRIGGER IF NOT EXISTS trg_borrow_delete` |
| [`accessDB.py`](accessDB.py:1) | 新增 `borrow_book()` 和 `return_book()` 两个方法 |
| [`repl.py`](repl.py:103) | `.borrow` 简化为调用 `borrow_book()`；新增 `.return` 命令 |

## 六、触发器与存储过程的职责边界

| 职责 | 触发器 | Python 存储过程 |
|------|:---:|:---:|
| 参数类型校验 | | ✅ |
| 用户/书存在性检查 | | ✅ |
| 借书上限检查 | | ✅ |
| 书已被借出检查 | ✅ (RAISE) | ✅ (提前检查给友好提示) |
| 自动更新 BOOK.status | ✅ | |
| 自动更新 USER.currentborrow | ✅ | |
| 外键约束检查 | ✅ | |
| borrowid 生成 | | ✅ |
| 友好错误提示 | | ✅ |

触发器作为**最后防线**保证数据一致性，Python 存储过程作为**业务逻辑层**提供友好交互。
