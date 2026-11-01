# 权限（RBAC）

## 1. 角色层级

```python
ROLE_LEVEL = {"root": 2, "admin": 1, "user": 0, "ALL": -1}
```

| 角色 | 来源 | 说明 |
|---|---|---|
| `root` | `bot_data/root.json` 或 `AULLBOT_ROOT` 环境变量（**aullbot 自己维护**） | **全局**权限 |
| `admin` | 会话配置 `rbac.list.admin`（群主自动算） | **本会话**最高权限 |
| `user` | 其余所有人 | 普通用户 |
| `ALL` | — | 特殊：**跳过黑名单检查**，用于"任何人都能用"的命令 |

## 2. 两个装饰器

```python
from aullbot.rbac import require_role, require_role_async

@command("/a")
@require_role("user")            # 同步命令
def a(text: str = "") -> str: ...

@command("/b")
@require_role_async("user")      # 异步命令
async def b(text: str = "") -> str: ...
```

**同步函数配 `require_role`，异步函数配 `require_role_async`**，写反会出问题：

| 组合 | 后果 |
|---|---|
| `async def` + `require_role` | 返回未 await 的协程，命令"有反应但不回复" |
| `def` + `require_role_async` | 调用变成协程但内部是同步逻辑，权限检查仍生效，但语义混乱 |

框架在 `find_command` 里有 `inspect.isawaitable(ret)` 兜底，但不要依赖。

## 3. 行为

装饰器做三件事：

1. **黑名单**：`sender_id in chat_config["blacklist"]` → 直接返回 `fail_return`
2. **定角色**：`root` / `admin` / `user`
3. **等级比较**：`ROLE_LEVEL[current] < ROLE_LEVEL[required]` → 返回 `fail_return`

`fail_return` 默认 `"No permission"`，可以自定义：

```python
@require_role("admin", fail_return="只有管理能用哦")
```

特殊值 `ALL`（等级 -1）会让黑名单检查失效（`> -0.1` 判断），用于"谁都能用"的命令。

## 4. 角色是怎么确定的

### root 的来源（aullbot 自己维护）

`config.yaml` 归 ncatbot 管，aullbot 不依赖它。root 按顺序取：

```
1. 环境变量 AULLBOT_ROOT      （.env，逗号分隔，设置后完全接管）
2. bot_data/root.json         （{"root": ["123"]} 或 ["123"]）
3. ncatbot 配置的 root         （兜底，兼容老部署）
```

会话配置里**不再有** `rbac.list.root` 字段（模板和所有会话配置都已删除）：
root 只能来自上面三个全局来源，避免群管理员改本群配置提权。



```python
# 群聊
sender_id = event.sender.user_id
group_role = context.get_user_role()          # QQ 群里的 owner/admin
admin_list = chat_config["rbac"]["list"]["admin"]

if 在 root 列表        → root
elif 在 admin 列表     → admin
elif group_role 是群主/管理员 → admin
else                  → user

# 私聊
user_role = "owner"    # 一律按 owner 处理 ⚠️（只会得到 admin，不是 root）
```

## 5. 私聊的权限（是设计，不是漏洞）

```python
# main.py is_private_me()
context.set_context(bot, TYPE_PRVATE, event.user_id, ..., user_role="owner", ...)
```

私聊一律按会话最高权限处理，**这是有意的**：

- 每个私聊是**独立会话**，有自己的 `config.json`、自己的提示词
- `admin` 的语义是"本会话最高权限"，不是全局
- 陌生人和 bot 私聊，能把**自己那个会话**的提示词改成任何样子——那是他个人的对话风格，碰不到别人

所以"陌生人私聊能执行 admin 命令"不是安全问题，**只要 admin 命令都只作用于本会话**。

真正需要警惕的是**全局操作**，那属于 `root`：

```python
@command("/module")
@require_role_async("root")     # 影响整个进程，admin 不够
```

当前分类：

| 命令 | 级别 | 作用域 |
|---|---|---|
| `/set-prompt`、`/ban`、`/add-admin` 等 | admin | 本会话 |
| `/module enable\|disable` | **root** | **全局** |
| `/bili-sub`、`/bili-list` | user | 本会话 |

## 6. 会话配置结构

`bot_data/group/<群号>/config.json`：

```json
{
  "blacklist": [123456],
  "rbac": {
    "list": {
      "admin": [111111, "$GROUP_OWNER"],
      "user": []
    }
  },
  "prompt": [{"role": "system", "content": "你是群助理"}]
}
```

| 字段 | 说明 |
|---|---|
| `blacklist` | 这些 QQ 号的命令全部拒绝 |
| `rbac.list.admin` | 管理员列表，`$GROUP_OWNER` 表示"群主自动是管理员" |
| `rbac.permissions.*` | 权限点定义（`root`/`admin`/`user` 各能做什么），**不是用户列表** |
| `prompt` | 该会话的 AI 系统提示词，为空则用全局 `system_prompt.json` |

## 7. 配置缓存

`get_cached_config()` 每个会话缓存 60 秒（`CACHE_TTL`）。

改完配置要让它生效，两种方式：

```python
from aullbot.rbac import invalidate_config_cache
invalidate_config_cache()      # 代码里主动失效
```

或者等 60 秒。

> 症状：改了 `config.json`，命令还是不认新管理员 → 就是缓存。

## 8. 坑：配置读不到会崩

`HistoryManager.read_json()` 在文件不存在时返回 `[]`。
如果 `load_config()` 直接返回它，`chat_config.get("blacklist")` 会炸：

```
AttributeError: 'list' object has no attribute 'get'
```

现在 `load_config()` 已兜底：

```python
data = self.read_json(chat_data)
if not isinstance(data, dict):
    return {}
return data
```

写新代码时仍要注意：**不要假设配置文件一定存在**。
