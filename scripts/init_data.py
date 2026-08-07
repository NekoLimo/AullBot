# scripts/init_data.py
from pathlib import Path
import json

BASE_DIR = Path(__file__).parent.parent
PROMPT_MD_PATH = BASE_DIR / "scripts" / "assets" / "system_prompt.md"
PROMPT_JSON_PATH = BASE_DIR / "bot_data" / "system_prompt.json"

group_dir = BASE_DIR / "bot_data" / "group"
group_dir.mkdir(parents=True, exist_ok=True)

private_dir = BASE_DIR / "bot_data" / "private"
private_dir.mkdir(parents=True, exist_ok=True)

with open(group_dir / "group_list.json","w",encoding="utf-8") as f:
    json.dump([], f, 
    ensure_ascii=False, 
    indent=2)
with open(private_dir / "private_list.json","w",encoding="utf-8") as f:
    json.dump([], f, 
    ensure_ascii=False, 
    indent=2)

try:
    with open(PROMPT_MD_PATH, "r", encoding="utf-8") as f:
        prompt = f.read()
except FileNotFoundError:
    with open(PROMPT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("You are a helpful assistant")
    prompt = "You are a helpful assistant"


with open(PROMPT_JSON_PATH,"w",encoding="utf-8") as f:
    json.dump(
    {
       "role": "system",
       "content": prompt
    }, f, 
    ensure_ascii=False, 
    indent=2
    )