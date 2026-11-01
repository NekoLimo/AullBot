# 会话历史

## 1. HistoryManager

单例在 `history_utils.py` 末尾：

```python
_HIST_ROOT = Path(__file__).parents[2] / "bot_data"     # 绝对路径
manager = HistoryManager(str(_HIST_ROOT))
```

> 用**绝对路径**而不是 `./bot_data`，避免工作目录不同导致读不到数据。

构造：

```python
from aullbot.history_utils import HistoryManager, manager

mgr = HistoryManager("/path/to/bot_data")   # 自定义根目录（测试用）
```

## 2. 磁盘布局

```
bot_data/
├── template_config.json            新会话配置模板
├── system_prompt.json              全局 AI 提示词
├── group_list.json                 已知群号列表
├── group/
│   ├── group_list.json
│   └── <群号>/
│       ├── history.json            对话历史
│       └── config.json             该群配置（权限/提示词）
├── private/
│   ├── private_list.json
│   └── <QQ号>/
│       ├── history.json
│       └── config.json
└── bilibili_subs.json              模块自己的数据
    bilibili_state.json
    modules.json
```

## 3. 常用 API

```python
mgr.chat_exists(chat_id, chat_type) -> bool
mgr.add_chat_list(chat_id, chat_type)          # 首次见到就建目录+复制模板
mgr.read_history(chat_id, chat_type) -> list
mgr.save_history(chat_id, chat_type, messages)  # 覆盖写
mgr.load_config(chat_id, chat_type) -> dict     # 一定返回 dict
mgr.read_json(path) -> Any
```

`chat_type`：`0` 群 / `1` 私聊。

## 4. 原子写

所有写操作走 `atomic_write_json`：

```python
tmp = <同目录临时文件>
写 tmp → os.fsync → os.replace(tmp, target)
```

好处：
- 断电/崩溃不会留下**半个文件**
- `os.replace` 在同一文件系统上是原子的
- 保留原文件的权限位

临时文件必须放**同一目录**（跨分区 `os.replace` 会失败）。

## 5. read_json 的返回值

```python
@staticmethod
def read_json(file_path: str) -> Any:
    if not os.path.exists(file_path):
        return []          # ← 注意：任何缺失文件都返回 []
    ...
```

它同时服务 list（`history.json`、`*_list.json`）和 dict（`config.json`），
所以缺失时统一返回 `[]`。

**配置侧必须自己兜底**：

```python
data = self.read_json(chat_data)
if not isinstance(data, dict):
    return {}
```

否则 `chat_config.get("blacklist")` 会抛 `AttributeError: 'list' object has no attribute 'get'`。

## 6. 会话初始化

`add_chat_list()` 做了三件事：

```text
1. 把 chat_id 追加到 group_list.json / private_list.json
2. mkdir bot_data/<type>/<id>/
3. 写空 history.json + 从 template_config.json 复制 config.json
```

`main.py` 在每条群消息进来时检查 `chat_exists()`，不存在就调用它。
所以**正常情况下不会出现"目录在但配置缺失"**——除非模板文件丢了或被手工删过。

## 7. AI 历史

`chat.py` 的流程：

```python
messages = manager.read_history(chat_id, chat_type)   # 读
messages.append({"role": "user", "content": metadata})
await call_loop(...)                                   # 调模型（可能多轮工具）
manager.save_history(chat_id, chat_type, messages)     # 覆盖写
```

历史会**无限增长**，目前没有截断逻辑（见 `TODO.md`）。
token 超限时模型会报错，届时需要加滑动窗口或摘要。

## 8. 测试时注意

`manager` 是模块级单例，测试里要替换而不是改 cwd：

```python
import aullbot.chat as chat
from aullbot.history_utils import HistoryManager

chat.manager = HistoryManager("/tmp/test_bot_data")   # ✅
```

改 cwd 对单例**无效**（它用的是绝对路径）。
