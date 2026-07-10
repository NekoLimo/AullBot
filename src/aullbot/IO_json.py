# scr/IO_json.py
import json
import os

_json_path = None
cue_words = None

def set_json_path(jsonph):
    global _json_path
    _json_path = jsonph
    with open(os.path.join(_json_path,"prompt.json"), "r", encoding="utf-8") as f:
        global cue_words
        cue_words = json.load(f)

def read_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        group_list = json.load(f)
        return group_list

def scroll_window(conversation_length, history):
    # 保护系统消息，如果只有系统消息则无需处理
    if len(history) <= 1:
        return h

    max_allowed = 1 + conversation_length * 2   # 系统消息 + conversation_length 轮完整对话

    # 当长度超过限制，或者长度为奇数（末尾不完整）时，移除最早的一对
    while len(history) > max_allowed or len(history) % 2 == 1:
        # 确保至少有三条（系统+一对）才能移除
        if len(history) >= 3:
            # 移除索引1（最早的用户消息），此时原索引2变为新的索引1
            history.pop(1)
            # 再移除新的索引1（对应的助手消息）
            history.pop(1)
        else:
            # 无法移除一对，终止循环
            break
    return history

def is_group_exists(group_id):
    file_path = os.path.join(_json_path,"group_list.json")
    group_list = read_json(file_path)
    if group_id in group_list:
        return True
    else:
        return False

def add_group_list(group_id):
    file_path = os.path.join(_json_path,"group_list.json")
    with open(file_path, "r", encoding="utf-8") as f:
        group_list = json.load(f)
        group_list.append(group_id)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(group_list, f, ensure_ascii=False)
    with open(os.path.join(_json_path,f"{group_id}.json"), "w", encoding="utf-8") as f:
        json.dump(cue_words, f, ensure_ascii = False)

def read_history(group_id):
    file_path = os.path.join(_json_path,f"{group_id}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        history = json.load(f)
    return history
 
def add_history(group_id,content):
    file_path = os.path.join(_json_path,f"{group_id}.json")
    history = read_history(group_id)
    with open(file_path, "w", encoding="utf-8") as f:
        history.append(content)
        json.dump(history, f, ensure_ascii=False, indent=2)

def write_json(group_id, history):
    file_path = os.path.join(_json_path, f"{group_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
