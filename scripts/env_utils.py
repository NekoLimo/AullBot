#!/usr/bin/env python3
"""`.env` 读写 + 交互式提问的公共工具（scripts/ 下共用）。

约定：
  * `.env` 每行形如 `export KEY="value"`，读写都兼容有无 `export`/引号
  * 写文件前备份成 `.env.bak`，写临时文件再 replace，权限固定 600
  * 非交互环境（管道/CI）里提问自动取默认值，不会卡住
"""
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

# 行缓冲：保证提问和提示按顺序出现（重定向到文件/管道时也不会错位）
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


# ---------------------------------------------------------------- 读
def read_env(path: Path | None = None) -> dict[str, str]:
    """读 `.env` 成 dict（去掉 export 前缀与引号）。"""
    target = path or ENV_FILE
    values: dict[str, str] = {}
    if not target.exists():
        return values
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:]
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# ---------------------------------------------------------------- 写
def write_values(mapping: dict[str, str], path: Path | None = None) -> Path:
    """把 mapping 写进 `.env`：已存在的键就地替换，其余行原样保留。

    只写非空值；空值跳过（避免把已有内容清空）。
    """
    target = path or ENV_FILE
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + ".bak"))

    updated: set[str] = set()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for key, value in mapping.items():
            if not value:
                continue
            if stripped.startswith(f"export {key}=") or stripped.startswith(f"{key}="):
                lines[index] = f'export {key}="{value}"'
                updated.add(key)
                break

    for key, value in mapping.items():
        if key in updated or not value:
            continue
        lines.append(f'export {key}="{value}"')

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    os.chmod(target, 0o600)
    return target


# ---------------------------------------------------------------- 显示
def mask(value: str, keep: int = 4) -> str:
    """密钥打码：保留头尾各 keep 个字符。"""
    if not value:
        return "（空）"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


# ---------------------------------------------------------------- 交互
def ask(question: str, default: str = "", secret: bool = False,
        assume_yes: bool = False) -> str:
    """问一句，返回输入；非交互或 --yes 时直接返回默认值。"""
    if assume_yes:
        return default
    suffix = f" [{default}]" if default else ""
    try:
        if secret and sys.stdin.isatty():
            import getpass

            answer = getpass.getpass(f"{question}{suffix}: ")
        else:
            answer = input(f"{question}{suffix}: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    answer = answer.strip()
    return answer or default


def confirm(question: str, default: bool = True, assume_yes: bool = False) -> bool:
    """是/否确认。"""
    if assume_yes:
        return default
    hint = "Y/n" if default else "y/N"
    try:
        answer = input(f"{question} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not answer:
        return default
    return answer in ("y", "yes", "是", "1")


def choose(question: str, options: list[str], default: int = 1,
           assume_yes: bool = False) -> int:
    """单选，返回 1-based 序号。"""
    print(question)
    for index, label in enumerate(options, 1):
        mark = "（默认）" if index == default else ""
        print(f"  [{index}] {label}{mark}")
    if assume_yes:
        return default
    raw = ask("选择", str(default))
    try:
        picked = int(raw)
        return picked if 1 <= picked <= len(options) else default
    except (TypeError, ValueError):
        return default


def ask_multiline(question: str, assume_yes: bool = False) -> str:
    """多行输入，空行结束。"""
    print(f"{question}（空行结束，Ctrl+C 取消）")
    if assume_yes:
        return ""
    lines: list[str] = []
    try:
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        print()
    return "\n".join(lines).strip()
