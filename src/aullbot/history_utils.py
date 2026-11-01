# src/aullbot/history_utils.py
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Union
import shutil

if TYPE_CHECKING:  # 仅类型检查；运行时用鸭子类型判断，避免拖入 openai（约 3~6 秒）
    from openai.types.chat import ChatCompletionMessage
else:
    ChatCompletionMessage = Any

TYPE_MAP = {0: "group", 1: "private"}


def _atomic_replace(src: str, dst: str) -> None:
    """把已经写好的临时文件换到目标位置（同一目录，os.replace 原子生效）。"""
    try:
        # mkstemp 建的是 0600，替换前对齐目标原权限（不存在则用 0644）
        try:
            mode = os.stat(dst).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        os.chmod(src, mode)
        os.replace(src, dst)
    except BaseException:
        _remove_quietly(src)
        raise


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def atomic_write_json(path: str, data: Any, indent: int | None = None) -> None:
    """原子写入 JSON：先写同目录唯一临时文件，fsync 后 os.replace 覆盖目标。

    - 崩溃/异常只会留下临时文件，目标文件要么是旧内容、要么是完整新内容
    - 临时文件名唯一，并发写同一路径时不会互相截断
    """
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        _remove_quietly(tmp)
        raise
    _atomic_replace(tmp, path)


def atomic_copy(src: str, dst: str) -> None:
    """原子复制：先复制到同目录临时文件，再替换目标。"""
    directory = os.path.dirname(dst) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
    except BaseException:
        _remove_quietly(tmp)
        raise
    _atomic_replace(tmp, dst)


def _is_sdk_message(obj) -> bool:
    """判断是不是 openai 的 ChatCompletionMessage，而不 import openai。

    openai 包导入要 3~6 秒，而我们只在这一处需要类型判断，
    用鸭子类型足够（有 role/content 且能 model_dump 的就是）。
    """
    return (
        not isinstance(obj, dict)
        and hasattr(obj, "role")
        and hasattr(obj, "content")
    )


def serialize_messages(
    messages: List[Union[Dict[str, Any], ChatCompletionMessage]],
) -> List[Dict[str, Any]]:
    """将可能包含 ChatCompletionMessage 对象的消息列表转为纯字典列表"""
    serialized = []
    for msg in messages:
        if isinstance(msg, dict):
            # 如果已经是字典，但内部可能嵌套了 tool_calls 对象（极少见），这里简单复制
            # 可安全拷贝
            msg_copy = msg.copy()
            # 若包含 tool_calls 且是 SDK 对象，需要转换（但通常字典格式下 tool_calls 也是字典）
            if "tool_calls" in msg_copy and msg_copy["tool_calls"]:
                # 如果第一个元素有 id 属性（对象）则转换，否则保持不变
                if hasattr(msg_copy["tool_calls"][0], "id"):
                    msg_copy["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg_copy["tool_calls"]
                    ]
            serialized.append(msg_copy)
        elif _is_sdk_message(msg):
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.refusal is not None:
                msg_dict["refusal"] = msg.refusal
            # 其他字段如 annotations, audio 可忽略，或按需添加
            serialized.append(msg_dict)
        else:
            raise TypeError(f"Unsupported message type: {type(msg)}")
    return serialized


# 反序列化其实就是直接返回，因为存储的就是字典，无需额外转换
def _deserialize_messages(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return data


class HistoryManager:
    def __init__(self, hist_path: str):
        self.hist_path = hist_path  # bot_data 根目录

    @staticmethod
    def read_json(file_path: str) -> Any:
        if not os.path.exists(file_path):
            return []
        with open(file=file_path, mode="r", encoding="utf-8") as f:
            return json.load(f)

    def chat_exists(self, chat_id: int | str, chat_type: int) -> bool:
        # 统一转为字符串比较，避免类型不一致
        chat_id = int(chat_id)

        # 映射 chat_type 到子路径
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")

        file_path = os.path.join(self.hist_path, sub_path, f"{sub_path}_list.json")
        try:
            with open(file=file_path, mode="r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.add_chat_list(chat_id=chat_id, chat_type=chat_type)
            return False  # 文件不存在或内容非法，视作不存在
        return chat_id in data

    def add_chat_list(self, chat_id: str | int, chat_type) -> None:
        chat_id = int(chat_id)
        sub_path: str | None = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")

        chat_list_path: str = os.path.join(
            self.hist_path, sub_path, f"{sub_path}_list.json"
        )
        chat_list: Any = self.read_json(chat_list_path)
        if chat_id not in chat_list:
            chat_list.append(chat_id)
            atomic_write_json(chat_list_path, chat_list)

        chat_history: str = os.path.join(self.hist_path, sub_path, f"{chat_id}")
        if not os.path.exists(chat_history):
            os.makedirs(chat_history, exist_ok=True)
            atomic_write_json(os.path.join(chat_history, "history.json"), [])
            atomic_copy(
                os.path.join(self.hist_path, "template_config.json"),
                os.path.join(chat_history, "config.json"),
            )

    def read_history(self, chat_id: str | int, chat_type: int) -> list[dict]:
        chat_id = str(chat_id)
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")
        chat_data: str = os.path.join(self.hist_path, sub_path, chat_id, "history.json")
        return self.read_json(chat_data)

    """
    def add_history(self, chat_id: int | str, chat_type: int, content: dict) -> None:
        history = self.read_history(chat_id=chat_id, chat_type=chat_type)
        history.append(content)
        self.write_json(chat_id=chat_id, chat_type=chat_type, content=history)
    """

    def write_history(self, chat_id: int | str, chat_type: int, content: Any) -> None:
        chat_id = str(chat_id)
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")
        chat_data: str = os.path.join(self.hist_path, sub_path, chat_id, "history.json")
        # 如果 content 是列表且包含 SDK 对象，则序列化
        if isinstance(content, list) and content:
            # 检查第一个元素是否可能是 SDK 对象
            if isinstance(content[0], dict) or _is_sdk_message(content[0]):
                content = serialize_messages(content)
        atomic_write_json(chat_data, content, indent=2)

    def save_history(
        self,
        chat_id: int | str,
        chat_type: int,
        messages: List[Union[Dict, ChatCompletionMessage]],
    ) -> None:
        """保存完整的消息历史（覆盖写入）"""
        self.add_chat_list(chat_id=chat_id, chat_type=chat_type)
        self.write_history(chat_id, chat_type, messages)

    def load_config(
        self,
        chat_id: int | str,
        chat_type: int,
    ) -> Any:
        chat_id = str(chat_id)
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")
        chat_data: str = os.path.join(self.hist_path, sub_path, chat_id, "config.json")
        data = self.read_json(chat_data)
        # read_json 在文件缺失时返回 []（历史上同时用于 list 和 dict），
        # 配置一律兜成 dict，避免调用方 .get() 抛 AttributeError
        if not isinstance(data, dict):
            if os.path.exists(chat_data):
                print(f"[history] 配置内容不是 dict（{type(data).__name__}），按空配置处理: {chat_data}")
            return {}
        return data

    def save_config(self, chat_id, chat_type, content):
        chat_id = str(chat_id)
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")
        chat_data: str = os.path.join(self.hist_path, sub_path, chat_id, "config.json")
        atomic_write_json(chat_data, content, indent=2)


# ==================== 全局单例 ====================
# 所有模块共用同一个实例；路径基于包所在位置，不依赖启动时的工作目录
# 写法与 main.py 的 BASE_DIR 保持一致（都不 resolve），软链接路径下也不会分叉
_HIST_ROOT = Path(__file__).parents[2] / "bot_data"
manager = HistoryManager(str(_HIST_ROOT))
