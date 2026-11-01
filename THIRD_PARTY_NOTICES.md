# 第三方字体许可与归属声明

> 本文件说明 `img.py` 使用的第三方字体及其许可义务。
> **不是法律意见**；涉及公开分发/商业使用时，请以官方许可原文为准，必要时咨询律师。
>
> 最后更新：2026-11-01

## 1. 当前使用的字体

`src/aullbot/tools/img.py` 直接读取 `fonts/` 下的两份源字体：

| 文件 | 内部名 / 版本 | 版权 | 许可 | 再分发 |
|---|---|---|---|---|
| `fonts/JetBrainsMonoNerdFont-Regular-v1.2.ttf` | JetBrainsMono Nerd Font Regular；`2.304` + Nerd Fonts `3.2.1` | © 2020 The JetBrains Mono Project Authors | OFL 1.1，无 RFN | ✅ |
| `fonts/SourceHanSansCN-Regular.otf` | Source Han Sans CN Regular；`2.005` | © 2014-2025 Adobe | OFL 1.1，**RFN `Source`** | ✅ |

两份都是 OFL 1.1，可以随仓库/产品再分发；条件是保留版权声明与 OFL 全文，
且修改版整体继续以 OFL 1.1 分发。详见 §3。

## 2. `img.py` 的字体策略

- `auto`（默认）：ASCII / 拉丁 / 符号 → JetBrains Mono；CJK / 全角 → Source Han Sans；
  Nerd Fonts 图标区（PUA）→ JetBrains Mono；
- `mono`：整图强制 JetBrains Mono；
- `sans`：整图强制 Source Han Sans；
- 通过环境变量 `AULLBOT_IMG_FONT=auto|mono|sans` 切换（重启生效）；
- 字体按仓库根目录定位（`Path(__file__).parents[3] / "fonts"`），不依赖启动时的工作目录；
- 单个字体缺失时回退到另一种，两个都缺失才报错。

## 3. 许可义务

- 随附两份版权声明与 OFL 全文（见 [`LICENSES/`](LICENSES/)）；
- 如果以后修改字体文件，修改版必须**整体**继续以 OFL 1.1 分发，不得改用其它许可；
- 不得单独售卖字体本身；
- Source Han Sans 的 Reserved Font Name 是 `Source`：**衍生字体的名称中不得使用 `Source`**；
- 不得暗示 Adobe / JetBrains / Nerd Fonts 对本项目背书；
- “JetBrains Mono is a trademark of JetBrains s.r.o.”、“Source is a trademark of Adobe”，
  OFL 不授予商标权；
- Nerd Fonts 补丁字体聚合了多种图标字形（Font Awesome、Material Design Icons 等），
  各自许可见 Nerd Fonts 的
  [license-audit.md](https://github.com/ryanoasis/nerd-fonts/blob/master/license-audit.md)。

## 4. 常见问题（FAQ）

### Q1：`fonts/` 里的两个字体能再分发吗？

可以，两个都是 OFL 1.1。随附版权声明与 OFL 全文；修改版整体继续以 OFL 分发；
Source Han Sans 的衍生字体名称不得使用 `Source`。

### Q2：`img.py` 需要别的字体文件吗？

不需要。`img.py` 只读取 `fonts/` 下的这两份字体，按字符自动切换。

### Q3：怎么临时换字体？

```bash
AULLBOT_IMG_FONT=mono ./scripts/run.sh dev
```

可选 `auto` / `mono` / `sans`，重启生效。

## 5. 许可文件索引

| 文件 | 说明 |
|---|---|
| [`LICENSES/JetBrainsMono-OFL.txt`](LICENSES/JetBrainsMono-OFL.txt) | JetBrains Mono 的 OFL 1.1 全文（含版权头） |
| [`LICENSES/SourceHanSans-OFL.txt`](LICENSES/SourceHanSans-OFL.txt) | Source Han Sans 的 OFL 1.1 全文（含 Adobe 版权与 RFN） |
| [`LICENSES/NerdFonts-MIT.txt`](LICENSES/NerdFonts-MIT.txt) | Nerd Fonts 源码的 MIT 许可 |
| [`fonts/README.md`](fonts/README.md) | `fonts/` 字体清单、渲染策略与许可义务 |

> 本文件只覆盖第三方字体。仓库代码本身的许可证由项目作者另行决定。
