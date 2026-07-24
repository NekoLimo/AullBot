# script/prompt.py
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PROMPT_MD_PATH = BASE_DIR / ".history" / "system_prompt.md"
PROMPT_JSON_PATH = BASE_DIR / ".history" / "system_prompt.json"

with open(str(PROMPT_MD_PATH), "r", encoding="utf-8") as f:
    prompt = f.read()


with open(str(PROMPT_JSON_PATH),"w",encoding="utf-8") as f:
    json.dump(
    {
       "role": "system",
       "content": prompt
    }, f, 
    ensure_ascii=False, 
    indent=2
    )
