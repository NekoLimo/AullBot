# scr/llm.py
import os
from openai import OpenAI


client = OpenAI(api_key=os.environ.get('DEEPSEEK_API_KEY'),  base_url="https://api.deepseek.com")

def result(role, text):
    return {"role": role, "content": text}

def dialogue(history):
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=history,
        stream=False
    )
    return response
    
"""
TODO

多句回复
文件
mcp
...

"""
