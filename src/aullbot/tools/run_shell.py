#!/usr/bin/env python3
# -*- coding: utf-8 -*-


################################################################################
# 此模块由AI编写，不保证安全性，如果不使用，请不要在 src/aullbot/tools/__init__.py 中导入#
################################################################################
"""
安全沙盒命令执行模块

功能：
  在固定沙盒目录中执行受限 Linux 命令，支持：
    - 白名单命令（不含 sed/awk）
    - 路径检查（防御绝对路径、目录穿越、符号链接逃逸）
    - 紧连选项路径提取（如 -ffile）
    - 输出大小限制（1MB）与超时（可配置）
    - 资源限制（CPU、内存、文件大小）
    - 强制关闭标准输入
    - 环境变量完全重建（脱敏）
    - 日志脱敏（不记录参数）

警告（高危）：
  1. TOCTOU 竞争：本模块基于用户态路径检查，在检查与执行之间存在时间窗口，
     攻击者可利用此窗口替换文件为符号链接逃逸沙盒。
     -> 生产环境务必配合容器、bubblewrap 或 nsjail 等 OS 级隔离。
  2. 多线程风险：若在多线程程序中使用 preexec_fn，可能导致死锁。
     -> 若需多线程，请设置 PREEXEC_FN_ENABLED = False，或使用进程池。

使用方法：
  from sandbox import run_shell_command
"""

import os
import shlex
import signal
import subprocess
import select
import time
import logging
import sys
from typing import Optional, List, Set
from aullbot.command_registry import ai_tools

# ============================= 可调配置 =============================
SECURE_BASE_DIR = os.path.abspath("/var/sandbox")   # 沙盒根目录
os.makedirs(SECURE_BASE_DIR, mode=0o700, exist_ok=True)

TMPDIR = os.path.join(SECURE_BASE_DIR, "tmp")
os.makedirs(TMPDIR, mode=0o700, exist_ok=True)

MAX_OUTPUT_SIZE = 1024 * 1024          # 1MB
DEFAULT_TIMEOUT = 5                    # 秒
ALLOW_RM_RF = False                    # 禁止 rm -rf
PREEXEC_FN_ENABLED = True              # 是否启用资源限制（多线程环境可关闭）

# 资源限制（仅当 PREEXEC_FN_ENABLED=True 时生效）
RESOURCE_LIMITS = {
    "cpu": 10,                         # CPU 秒数
    "as": 512 * 1024 * 1024,           # 512 MB 内存
    "fsize": 100 * 1024 * 1024         # 输出文件大小 100 MB
}

# ============================= 白名单 =============================
BASE_COMMANDS = {
    # 原有
    "ls", "cat", "echo", "grep", "head", "tail",
    "wc", "sort", "uname", "date", "whoami", "id", "pwd",
    "which", "tree", "du", "df", "uptime",
    # 新增：只读/信息
    "md5sum", "sha1sum", "sha256sum", "sha512sum",
    "basename", "dirname", "realpath", "readlink",
    "free", "nproc", "arch", "env", "printf",
    "od", "nl", "cmp"
}

EXTENDED_COMMANDS = {
    # 原有
    "mkdir", "touch", "cp", "mv", "rm", "ln",
    "chmod", "chown", "stat", "file",
    "cut", "uniq", "tr", "diff", "comm",
    "find",
    # 新增：沙盒内写操作或更复杂处理
    "gzip", "gunzip", "zcat",
    "bzip2", "bunzip2", "bzcat",
    "xz", "unxz", "xzcat",
    "tee", "split", "truncate",
    "paste", "join", "expand", "unexpand", "shuf",
    "xxd"
}

ALLOWED_COMMANDS = BASE_COMMANDS | EXTENDED_COMMANDS

# ============================= 日志（脱敏） =============================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

# ============================= 启动检查 =============================
def _check_sandbox():
    """检查沙盒目录是否存在且可写，若异常则提前失败"""
    if not os.path.isdir(SECURE_BASE_DIR):
        raise RuntimeError(f"沙盒目录 {SECURE_BASE_DIR} 不存在或不是目录")
    if not os.access(SECURE_BASE_DIR, os.W_OK):
        raise RuntimeError(f"沙盒目录 {SECURE_BASE_DIR} 不可写")
    # 检查 TMPDIR
    os.makedirs(TMPDIR, mode=0o700, exist_ok=True)
    if not os.access(TMPDIR, os.W_OK):
        raise RuntimeError(f"临时目录 {TMPDIR} 不可写")
_check_sandbox()

# ============================= 资源限制（子进程） =============================
def _set_resource_limits():
    """在子进程中设置资源限制，若失败则直接退出"""
    if sys.platform == "win32":
        return
    try:
        import resource
        limits = RESOURCE_LIMITS
        resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu"], limits["cpu"]))
        resource.setrlimit(resource.RLIMIT_AS, (limits["as"], limits["as"]))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits["fsize"], limits["fsize"]))
    except Exception:
        # 若设置失败，终止子进程并返回特殊码 126
        os._exit(126)

# ============================= 路径提取与校验 =============================
def _extract_path_from_arg(arg: str) -> Optional[str]:
    """
    从命令参数中提取可能的文件路径，支持：
      1. 长选项：--file=/path
      2. 短选项内含 '/'：-I/usr/include
      3. 短选项紧连文件名：-ffile（返回 file）
      4. 独立参数（不以 '-' 开头）
    """
    if arg.startswith('--') and '=' in arg:
        return arg.split('=', 1)[1]
    if arg.startswith('-') and len(arg) > 1 and arg[1] != '-':
        slash_pos = arg.find('/')
        if slash_pos != -1:
            return arg[slash_pos:]
        return arg[1:]   # 去掉 '-'，可能是选项名或紧连文件名
    return arg

def _is_safe_path(base_dir: str, user_path: str) -> bool:
    """
    检查路径是否在沙盒内，并防御符号链接逃逸。
    能正确处理不存在的路径，不会抛出异常。
    """
    if not user_path:
        return True

    # 若沙盒目录不存在或无法访问，直接拒绝
    if not os.path.exists(base_dir):
        return False

    try:
        full = os.path.normpath(os.path.join(base_dir, user_path))
        # 寻找最长存在的父路径
        existent = full
        while not os.path.exists(existent):
            parent = os.path.dirname(existent)
            if parent == existent:   # 到达根目录
                break
            existent = parent

        real_existent = os.path.realpath(existent)
        real_base = os.path.realpath(base_dir)

        # 存在的部分必须在沙盒内
        if not (real_existent == real_base or real_existent.startswith(real_base + os.sep)):
            return False

        # 剩余部分不能包含 '..' 逃逸
        remain = os.path.relpath(full, existent)
        if remain.startswith('..'):
            return False

        # 拼接并检查最终路径
        final_path = os.path.normpath(os.path.join(real_existent, remain))
        if not (final_path == real_base or final_path.startswith(real_base + os.sep)):
            return False

        return True
    except OSError:
        # 文件系统异常时保守拒绝
        return False

# ============================= 命令专项校验 =============================
def _validate_specific_command(cmd: str, args: List[str]) -> bool:
    if cmd == "find":
        dangerous = {"-delete", "-exec", "-ok", "-execdir", "-okdir"}
        for arg in args:
            if arg in dangerous:
                logger.warning("find 使用了危险选项（已拒绝）: 命令=%s", cmd)
                return False
    elif cmd == "rm":
        if not ALLOW_RM_RF and ({"-rf", "-fr"} & set(args)):
            logger.warning("rm -rf 被禁止: 命令=%s", cmd)
            return False
    return True

# ============================= 进程清理 =============================
def _kill_process_group(pid: int):
    try:
        os.killpg(pid, signal.SIGTERM)
        time.sleep(0.1)
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

# ============================= 主函数 =============================
@ai_tools("run_shell")
def run_shell_command(
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
    allowed_commands: Optional[Set[str]] = None
) -> str:
    """
    在沙盒中执行 Linux 命令（不支持管道/重定向）。
    白名单命令参见 ALLOWED_COMMANDS。
    输出限制 1MB，超时 5 秒。
    """
    if not command or not command.strip():
        return "命令不能为空"

    try:
        args = shlex.split(command)
    except ValueError:
        logger.warning("命令解析失败")
        return "命令格式解析失败"

    if not args:
        return "无效命令"

    cmd_name = args[0]
    if '/' in cmd_name:
        logger.warning("尝试使用路径命令: %s", cmd_name)
        return "命令格式不允许包含路径"

    if allowed_commands is None:
        allowed_commands = ALLOWED_COMMANDS
    if cmd_name not in allowed_commands:
        logger.warning("未授权命令: %s", cmd_name)
        return f"命令 '{cmd_name}' 不在允许列表中"

    # ----- 路径安全检查（不记录具体参数） -----
    for param in args[1:]:
        path_candidate = _extract_path_from_arg(param)
        if path_candidate is not None:
            if not _is_safe_path(SECURE_BASE_DIR, path_candidate):
                logger.warning("不安全的路径参数: 命令=%s", cmd_name)
                return "参数包含不安全的路径，已拒绝"

    # ----- 专项校验 -----
    if not _validate_specific_command(cmd_name, args[1:]):
        return f"命令 '{cmd_name}' 使用了禁止的选项"

    # ----- 环境变量（完全重建） -----
    env = {
        'PATH': '/usr/bin:/bin',
        'LANG': 'C',
        'TMPDIR': TMPDIR,
        'HOME': SECURE_BASE_DIR,
        'PWD': SECURE_BASE_DIR,
    }

    # ----- 启动子进程 -----
    try:
        preexec_fn = _set_resource_limits if (PREEXEC_FN_ENABLED and sys.platform != "win32") else None
        proc = subprocess.Popen(
            args,
            cwd=SECURE_BASE_DIR,
            stdin=subprocess.DEVNULL,          # 强制关闭标准输入
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            start_new_session=True,
            env=env,
            preexec_fn=preexec_fn
        )
    except FileNotFoundError:
        logger.error("命令未找到: %s", cmd_name)
        return f"命令 '{cmd_name}' 未找到"
    except Exception as e:
        logger.error("启动失败: %s", e, exc_info=True)
        return "命令执行异常"

    # ----- 读取输出（超时+大小限制）-----
    output_chunks = []
    total_size = 0
    deadline = time.monotonic() + timeout

    try:
        while True:
            now = time.monotonic()
            if now > deadline:
                _kill_process_group(proc.pid)
                logger.warning("命令超时被杀死: %s", cmd_name)
                return "命令执行超时（已终止）"

            remaining = deadline - now
            if remaining < 0:
                remaining = 0
            rlist, _, _ = select.select([proc.stdout], [], [], remaining)

            if rlist:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_OUTPUT_SIZE:
                    _kill_process_group(proc.pid)
                    logger.warning("命令输出超限: %s", cmd_name)
                    return f"命令输出超过 {MAX_OUTPUT_SIZE} 字节（已终止）"
                output_chunks.append(chunk)

            if proc.poll() is not None:
                # 读取剩余数据
                remaining_data = proc.stdout.read()
                if remaining_data:
                    total_size += len(remaining_data)
                    if total_size > MAX_OUTPUT_SIZE:
                        _kill_process_group(proc.pid)
                        return f"命令输出超过 {MAX_OUTPUT_SIZE} 字节（已终止）"
                    output_chunks.append(remaining_data)
                break

        # 检查返回码
        if proc.returncode == 126:
            return "资源限制设置失败，请检查系统配置"
        if proc.returncode != 0:
            logger.warning("命令返回非零码: %s, code=%d", cmd_name, proc.returncode)
            return "命令执行失败"

        full_output = ''.join(output_chunks)
        return full_output.rstrip('\n') or "(命令无输出)"

    except Exception as e:
        logger.error("未知异常: %s", e, exc_info=True)
        if proc.poll() is None:
            _kill_process_group(proc.pid)
        return "命令执行发生内部错误"


# ============================= 简单自测 =============================
if __name__ == "__main__":
    print(run_shell_command("ls -l"))
    print(run_shell_command("echo hello"))
    print(run_shell_command("cat /etc/passwd"))  # 应被拒绝