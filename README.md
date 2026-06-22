# 校园组织活动管理系统 Demo

这是一个简单的本地演示版本：

- 前端：单文件 HTML、CSS、JavaScript
- 后端：Python 标准库 HTTP 服务
- 数据库：SQLite
- 第三方依赖：无

## 启动

双击 `start-demo.bat`，或在当前目录运行：

```powershell
python server.py
```

然后访问：

```text
http://127.0.0.1:4173
```

数据库会自动创建在：

```text
data/campus_activity.sqlite3
```

## API

- `GET /api/health`：检查服务与数据库状态
- `GET /api/state`：读取系统数据
- `PUT /api/state`：保存系统数据

前端仍保留浏览器本地缓存作为后端未启动时的降级方案。

## 查看数据库内容

双击 `查看数据库.bat`，可以直接查看：

- 活动记录
- 参与和签到记录
- 操作日志

无需安装或学习 SQLite 管理工具。
