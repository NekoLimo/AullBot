# fonts/ — `img.py` 使用的字体

`src/aullbot/tools/img.py` **直接读取本目录的两份字体**，按字符自动切换，
不再合并成单一字体文件。两份均为 SIL Open Font License 1.1，可再分发。

| 文件 | 内部名 / 版本 | 版权 | 许可 | SHA-256 |
|---|---|---|---|---|
| `JetBrainsMonoNerdFont-Regular-v1.2.ttf` | JetBrainsMono Nerd Font Regular；`2.304` + Nerd Fonts `3.2.1` | © 2020 The JetBrains Mono Project Authors | OFL 1.1（无 Reserved Font Name） | `f968cf19ddd0335f1e452cbfa3df228784d081bd3e9f9b08c4b75ab4ca774929` |
| `SourceHanSansCN-Regular.otf` | Source Han Sans CN Regular；`2.005` | © 2014-2025 Adobe，**Reserved Font Name `Source`** | OFL 1.1 | `e2bc8a2e7f37474b774fff8db758681ece40bb6947a90d571bce9dd60671a8e4` |

## 渲染策略

`img.py` 的 `FONT_MODE`：

- `auto`（默认）：ASCII / 拉丁 / 符号 → JetBrains Mono；CJK / 全角 → Source Han Sans；
  Nerd Fonts 图标区（PUA）→ JetBrains Mono；
- `mono`：整图强制 JetBrains Mono；
- `sans`：整图强制 Source Han Sans。

切换方式（重启生效）：

```bash
AULLBOT_IMG_FONT=mono ./scripts/run.sh dev
```

单个字体文件缺失时会回退到另一种；两个都缺失才会报错。

## 许可义务

- 随附两份版权声明与 OFL 全文（见 [`../LICENSES/`](../LICENSES/)）；
- 如果以后修改字体文件，修改版整体继续以 OFL 1.1 分发，不得单独售卖字体本身；
- Source Han Sans 的 Reserved Font Name 是 `Source`：**衍生字体的名称中不得使用 `Source`**；
- 不要暗示 Adobe / JetBrains / Nerd Fonts 对本项目背书；
- Nerd Fonts 补丁字体聚合了多种图标字形（Font Awesome、Material Design Icons 等），
  各自许可见 [license-audit.md](https://github.com/ryanoasis/nerd-fonts/blob/master/license-audit.md)。

## 相关文件

- [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) — 完整的第三方字体说明
- [`../LICENSES/JetBrainsMono-OFL.txt`](../LICENSES/JetBrainsMono-OFL.txt)
- [`../LICENSES/SourceHanSans-OFL.txt`](../LICENSES/SourceHanSans-OFL.txt)
