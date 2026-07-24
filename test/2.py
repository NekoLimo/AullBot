import os
import time
start = time.perf_counter()
from openai import OpenAI
end = time.perf_counter()
print(f"------------- 导入耗时：{end - start:.4f} 秒 -------------")

client = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com")

start1 = time.perf_counter()
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "disabled"}}
)

print(response.choices[0].message.content)

end1 = time.perf_counter()
print(f"------------- API 调用耗时：{end1 - start1:.4f} 秒 -------------")