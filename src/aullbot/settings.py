# src/aullbot/settings.py
"""运行时配置：全部来自环境变量（可写在项目根目录的 `.env`）。

设计：
  * 先加载 `.env`（若存在），再读 `os.environ`
  * 所有项都有默认值，缺省即可运行
  * 非法值（如 effort 写了 "huge"）回退默认并打印一次警告
  * 名字统一用 `AULL_` / `LLM_` 前缀，避免和系统变量冲突

可用项（写进 `.env` 即可，无需改代码）：

    # 模型
    LLM_MODEL=deepseek-v4-pro
    LLM_BASE_URL=https://api.deepseek.com
    LLM_API_KEY=sk-...
    LLM_EFFORT=high               # low | high | max
    LLM_THINKING=disabled         # enabled | disabled
    LLM_MAX_TOOL_ITERATIONS=5

    # 其它
    AULL_TZ=Asia/Shanghai
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # 项目根目录
ENV_FILE = ROOT / ".env"

_warned: set[str] = set()


def load_dotenv(path: Path | None = None) -> None:
    """把 `.env` 读进 os.environ（不覆盖已存在的变量）。

    自己实现是为了不引入 python-dotenv 依赖；只支持最常见的
    `export KEY="value"` / `KEY=value` / `# 注释` 三种写法。
    """
    target = path or ENV_FILE
    if not target.exists():
        return
    for line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:]
        key, _, value = stripped.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        print(f"[settings] {message}")


def env_str(name: str, default: str) -> str:
    value = (os.environ.get(name) or "").strip()
    return value or default


def env_int(name: str, default: int, low: int | None = None,
            high: int | None = None) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _warn_once(name, f"{name}={raw!r} 不是整数，回退 {default}")
        return default
    if low is not None and value < low:
        _warn_once(name, f"{name}={value} 小于 {low}，按 {low} 处理")
        return low
    if high is not None and value > high:
        _warn_once(name, f"{name}={value} 大于 {high}，按 {high} 处理")
        return high
    return value


def env_choice(name: str, default: str, choices: tuple[str, ...]) -> str:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw not in choices:
        _warn_once(name, f"{name}={raw!r} 不在 {choices} 里，回退 {default}")
        return default
    return raw


# ---------------------------------------------------------------- 加载
load_dotenv()

# ---------------------------------------------------------------- 模型
MODEL: str = env_str("LLM_MODEL", "deepseek-v4-flash")
BASE_URL: str = env_str("LLM_BASE_URL", "https://api.deepseek.com")
API_KEY: str = env_str("LLM_API_KEY", "")
EFFORT: str = env_choice("LLM_EFFORT", "high", ("low", "high", "max"))
THINKING: str = env_choice("LLM_THINKING", "disabled", ("enabled", "disabled"))
MAX_TOOL_ITERATIONS: int = env_int("LLM_MAX_TOOL_ITERATIONS", 5, low=1, high=20)


def describe() -> str:
    """启动日志用：一眼看出当前用的哪套配置。"""
    key = "已设置" if API_KEY else "缺失"
    return (f"model={MODEL} base_url={BASE_URL} key={key} "
            f"effort={EFFORT} thinking={THINKING} "
            f"max_tool_iterations={MAX_TOOL_ITERATIONS}")
