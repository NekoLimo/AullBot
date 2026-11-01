# 常见陷阱

> 这些都是本项目真实踩过的坑，按「症状 → 原因 → 正确写法」组织。

## 1. async 函数配了同步装饰器

**症状**：命令有反应，但不回复；日志出现 `RuntimeWarning: coroutine 'xxx' was never awaited`。

**原因**：

```python
@command("/say")
@require_role("user")          # 同步包装器
async def say(...)             # 异步函数
```

`require_role` 返回的是同步 `wrapper`，调用它得到**一个协程对象**，
而 `inspect.iscoroutinefunction(wrapper)` 为 `False`，框架不会 await。

**正确**：

```python
@require_role_async("user")
async def say(...)
```

框架已在 `find_command` 加了 `inspect.isawaitable(ret)` 兜底，但别依赖。

---

## 2. 多参数命令会丢掉第 3 个词

**症状**：`/toggle a b c d` 只有 `a` `b` 生效。

**原因**：`func(*command_args[:len_params])`，超出参数个数的 token 被**静默丢弃**。

**正确**：内容可能含空格时用**单参数**，或者从原文自救：

```python
raw = context.get_raw_message()          # "/img a b c d"
text = re.search(r'^/img\s?(.*)', raw, re.DOTALL).group(1)
```

`/img` 就是这个模式（实测 `/img a b c d` 能完整渲染，不会只剩 `a`）。

**相关的坑**：布尔参数从命令行传进来是字符串，`"false"` 是 truthy，关不掉。

## 3. 空消息导致 IndexError

**症状**：日志出现 `-255` 和 `list index out of range`。

**原因**：用户发的是小程序卡片/图片，没有 `PlainText` 段 → `msg_text` 为空 →
`shlex.split("")` 得到 `[]` → `tokens[0]` 越界。

**状态**：被 `except Exception` 兜住，返回 `COMMAND_NOT_FOUND`，不影响功能。

**彻底修**（**框架维护者处理，模块作者不要改**）：`find_command` 开头加

```python
if not command.strip():
    return COMMAND_NOT_FOUND
```

---

## 4. 配置缺失返回 `[]` 而不是 `{}`

**症状**：`AttributeError: 'list' object has no attribute 'get'`

**原因**：`read_json()` 对缺失文件返回 `[]`（历史上同时服务 list 和 dict）。

**正确**：读配置一律走 `load_config()`（已兜底成 dict），或自己判断：

```python
data = mgr.read_json(path)
cfg = data if isinstance(data, dict) else {}
```

---

## 5. 工作目录不同导致读不到数据

**症状**：`/bili-list` 显示空、历史丢失、配置读不到。

**原因**：早期用 `./bot_data` 相对路径，从别的目录启动就指向了别处。

**正确**：`HistoryManager` 用绝对路径（已修）：

```python
_HIST_ROOT = Path(__file__).parents[2] / "bot_data"
manager = HistoryManager(str(_HIST_ROOT))
```

**副作用**：测试不能再靠 `cd` 到临时目录来隔离，要替换 `manager` 实例。

---

## 6. 状态判断把「空/0」当成「没有」

**症状**：每轮都重建基线；重复推送；任务反复初始化。

**原因**：`if not known_dyn`、`if not dyn_wm` —— `[]` 和 `0` 都是 falsy，
但「列表为空」和「还没建立过」是两回事。

**正确**：用显式标记判断"是否初始化过"：

```python
if "dyn_wm" not in cur:        # 而不是 not dyn_wm
    ...
cur["dyn_ready"] = True
```

---

## 7. 整体覆盖状态字典会丢字段

**症状**：`dyn_ready` / 水位线莫名消失，导致重复推送。

**原因**：

```python
state[uid] = {"dynamic": ..., "video": ...}   # ❌ 把其它字段冲掉了
```

**正确**：原地改

```python
cur = state.setdefault(uid, {})
cur["dynamic"] = ...
cur["dyn_ready"] = True
```

---

## 8. 接口返回条数会浮动

**症状**：突然推送几条几个月前的内容。

**原因**：`feed/all` 之类接口返回 12 条还是 16 条不固定，只按 id 去重会把
"新出现的旧内容"当成新增。

**正确**：**id + 时间水位线**双条件。详见 `bilibili_monitor._pick_fresh()`。

---

## 9. 用错接口（关注流 vs 空间）

**症状**：查某 UP 的动态永远是 0 条。

**原因**：`/x/polymer/web-dynamic/v1/feed/all` 是**关注动态**，未关注的 UP 返回空。

**正确**：`/x/polymer/web-dynamic/v1/feed/space?host_mid=<uid>&offset=`

---

## 10. 后台任务取消不掉

**症状**：`/module disable` 后任务还在跑；Ctrl+C 后进程不退出。

**原因**：任务吞掉了 `CancelledError`。

```python
except Exception:      # 这个抓不到 CancelledError（它是 BaseException）
    pass
except BaseException:  # ❌ 这个能抓到，然后你把取消吞了
    pass
```

**正确**：

```python
except asyncio.CancelledError:
    raise                      # 必须继续抛
except Exception as e:
    print(...)
```

---

## 11. 后台任务里用 context

**症状**：消息发错群，或 `RuntimeError: No context set`。

**原因**：后台任务没有请求上下文；`ContextVar` 在 `create_task` 时会复制，
可能残留**创建任务那一刻**的会话，非常隐蔽。

**正确**：目标会话作为参数传进去，用 `push` 发送。

---

## 12. 导入阶段做重活

**症状**：启动 20+ 秒。

**原因**：`tools/__init__.py` 会 import 所有模块，模块顶层 `import bpi` / `PIL` 等。

**正确**：重依赖放到函数内部延迟导入。

```python
def _build_client():
    from bpi import AsyncBpiClient      # 用到才导入
    ...
```

---

## 13. 模块文件没写 MODULE

**症状**：模块里的命令全部不生效，日志有

```
[tools] xxx.py 跳过（未声明 MODULE）
```

**原因**：`@command` 注册时找不到归属模块，被拒绝。

**正确**：文件顶层必须有

```python
MODULE = ModuleMeta(name="xxx", ...)
```

---

## 14. 改了配置文件没生效

| 文件 | 生效时机 |
|---|---|
| `.env` | 重启进程（`run.sh` 启动时 source） |
| `config.yaml` | 重启进程 |
| `bot_data/modules.json` | 重启进程 |
| `bot_data/<type>/<id>/config.json` | 60 秒缓存后，或 `invalidate_config_cache()` |

---

## 15. 推送失败导致监控静默死掉

**症状**：bot 还在，但再也不推送了。

**原因**：后台循环里 `await push.send_many(...)` 抛异常 → 整个 `while` 退出。

**正确**：`push` 本身不抛异常（已封装），但循环里仍要有兜底：

```python
while True:
    try:
        ...
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[xxx] 轮询异常: {type(e).__name__}: {e}")
    await asyncio.sleep(interval)
```
