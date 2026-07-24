# src/aullbot/history_utils.py
import json
import os
from openai.types.chat import ChatCompletionMessage
from typing import List, Dict, Any, Union
import shutil

TYPE_MAP = {0: 'group', 1: 'private'}

def serialize_messages(messages: List[Union[Dict[str, Any], ChatCompletionMessage]]) -> List[Dict[str, Any]]:
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
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in msg_copy["tool_calls"]
                    ]
            serialized.append(msg_copy)
        elif isinstance(msg, ChatCompletionMessage):
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
                            "arguments": tc.function.arguments
                        }
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
        self.hist_path = hist_path    # .history 根目录

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
        
        file_path = os.path.join(self.hist_path, sub_path, f'{sub_path}_list.json')
        try:
            with open(file=file_path, mode='r', encoding='utf-8') as f:
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
        
        chat_list_path: str = os.path.join(self.hist_path, sub_path, f"{sub_path}_list.json")
        chat_list: Any = self.read_json(chat_list_path)
        if chat_id not in chat_list:
            chat_list.append(chat_id)
            with open(file=chat_list_path, mode="w", encoding="utf-8") as f:
                json.dump(chat_list, f, ensure_ascii=False)
        
        chat_history: str = os.path.join(self.hist_path, sub_path, f'{chat_id}')
        if not os.path.exists(chat_history):
            os.makedirs(chat_history, exist_ok=True)
            with open(file=os.path.join(chat_history, "history.json"), mode="w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False)
            shutil.copy(os.path.join(self.hist_path, "template_config.json"), os.path.join(chat_history, "config.json"))
    
    def read_history(self, chat_id: str | int, chat_type: int) -> list[dict]:
        chat_id = str(chat_id)
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")
        chat_data: str = os.path.join(self.hist_path, sub_path, chat_id, "history.json")
        return self.read_json(chat_data)
    
    '''
    def add_history(self, chat_id: int | str, chat_type: int, content: dict) -> None:
        history = self.read_history(chat_id=chat_id, chat_type=chat_type)
        history.append(content)
        self.write_json(chat_id=chat_id, chat_type=chat_type, content=history)
    '''

    def write_json(self, chat_id: int | str, chat_type: int, content: Any) -> None:
        chat_id = str(chat_id)
        sub_path = TYPE_MAP.get(chat_type)
        if sub_path is None:
            raise ValueError("chat_type need 0 or 1")
        chat_data: str = os.path.join(self.hist_path, sub_path, chat_id, "history.json")
        # 如果 content 是列表且包含 SDK 对象，则序列化
        if isinstance(content, list) and content:
            # 检查第一个元素是否可能是 SDK 对象
            if isinstance(content[0], (dict, ChatCompletionMessage)):
                content = serialize_messages(content)
        with open(file=chat_data, mode="w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    def save_history(self, chat_id: int | str, chat_type: int, messages: List[Union[Dict, ChatCompletionMessage]]) -> None:
        """保存完整的消息历史（覆盖写入）"""
        self.add_chat_list(chat_id=chat_id, chat_type=chat_type)
        self.write_json(chat_id, chat_type, messages)
