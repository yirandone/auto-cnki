# auto-cnki

> 📚 **新闻传播学每日文献推送工具** —— 每天自动从知网（CNKI）检索指定期刊与议题的文献，
> 用 AI 精选 3 篇，附关键词、摘要与推荐理由，发送到你的邮箱。

基于 [`cnki-mcp`](https://github.com/SepineTam/cnki-mcp) 构建。

---

## ✨ 功能特性

- 📚 **多期刊 × 多关键词检索**：自由配置目标期刊与感兴趣的议题
- 🎯 **每日精选 3 篇**：按综合排序取候选，时间窗自动放宽，稳定输出
- 🤖 **DeepSeek 生成推荐理由**：每篇附一句「为什么值得看」
- 📧 **HTML 邮件推送**：含题目、作者、期刊、关键词、摘要、知网详情链接
- 🔁 **自动去重**：记录已推送文献，避免重复推荐
- 🗂️ **本地存档**：每日结果以 HTML 保存到 `digest_output/`
- ⏰ **可定时**：配合 Windows 计划任务，每天自动运行

---

## 🔄 工作原理

```
Windows 计划任务（每天 8:00）
        │
        ▼
daily_digest.py
  1. 用 cnki-mcp 检索「目标期刊 × 关键词」
  2. 按综合排序取候选，时间窗不够则自动放宽（30 → 90 → 365 天 → 不限）
  3. 选取前 3 篇，读取每篇详细信息（摘要 / 关键词）
  4. 调用 DeepSeek 为每篇生成一句推荐理由
  5. 读取 pushed.txt 去重
  6. 组装 HTML 邮件并发送
  7. 存档到 digest_output/ 并更新 pushed.txt
```

---

## 📦 前置要求

| 依赖 | 说明 |
|---|---|
| **Python 3.10+** | 运行环境 |
| **[uv](https://docs.astral.sh/uv/)** | Python 包管理工具 |
| **[cnki-mcp](https://github.com/SepineTam/cnki-mcp)** | 知网检索服务（本工具的数据源） |
| **DeepSeek API Key** | 生成推荐理由 |
| **QQ 邮箱 SMTP 授权码** | 发送邮件 |

---

## 🚀 快速开始

### 1. 安装 uv

**Windows（PowerShell）：**
```powershell
winget install --id=astral-sh.uv -e
```

**macOS / Linux：**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后**重开终端**，验证：
```bash
uv --version
```

### 2. 安装项目依赖

```bash
uv sync
uv add python-dotenv requests
```

### 3. 安装 Playwright 浏览器（cnki-mcp 需要）

```bash
uv run playwright install chromium
```

> 若下载慢，可先设国内镜像：
> ```powershell
> $env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright"
> uv run playwright install chromium
> ```

### 4. 初始化知网 Profile

```bash
uv run cnki-mcp init
```

按提示完成（Profile 名称直接回车用默认 `default`）。

### 5. 配置密钥

复制示例文件并填入你自己的密钥：

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
DEEPSEEK_API_KEY=你的DeepSeek密钥
QQ_EMAIL=你的QQ邮箱
QQ_SMTP_CODE=你的QQ邮箱SMTP授权码
```

> - **DeepSeek Key**：https://platform.deepseek.com → API Keys
> - **QQ 授权码**：QQ 邮箱 → 设置 → 账户 → 开启 SMTP 服务 → 获取授权码（**不是**QQ 密码）

### 6. 配置期刊与关键词

编辑 `daily_digest.py` 顶部配置区：

```python
JOURNALS = [
    "国际新闻界",
    "新闻与传播研究",
    "现代传播(中国传媒大学学报)",
    "新闻大学",
    "新闻记者",
]
TOPICS = ["算法推荐", "平台治理", "数字新闻", "情感传播"]

RESULT_COUNT = 3                          # 每天推送篇数
WINDOW_DAYS_TIERS = (30, 90, 365, 100000) # 时间窗阶梯（自动放宽）
```

> ⚠️ 期刊名须用**知网中的准确全称**。查询方法：
> ```bash
> uv run cnki-mcp tool issn --journal "期刊名"
> ```
> 例如「现代传播」在知网里是 `现代传播(中国传媒大学学报)`。

### 7. 运行

**空跑测试（不发邮件，只打印结果）：**
```bash
uv run python daily_digest.py --dry-run
```

**正式运行（发送邮件）：**
```bash
uv run python daily_digest.py
```

---

## ⏰ 定时运行（Windows 计划任务）

>暂未启用，待更新

---

## 📁 项目结构

```
auto-cnki/
├── daily_digest.py         # 主脚本
├── .env                    # 密钥配置（已 gitignore，不上传）
├── .env.example            # 密钥配置示例（占位符）
├── pushed.txt              # 已推送文献清单（自动生成，去重用）
├── digest_output/          # 每日推送结果存档（自动生成）
├── README.md               # 本文件
├── README_CNKI_MCP.md      # 上游 cnki-mcp 原始说明
└── ...
```

---

## ⚙️ 参数说明

### 命令行参数

| 参数 | 说明 |
|---|---|
| `--dry-run` | 只运行流程并打印结果，不发送邮件 |

### `daily_digest.py` 顶部可调参数

| 变量 | 说明 | 默认 |
|---|---|---|
| `JOURNALS` | 目标期刊列表 | 5 本新闻传播学核心期刊 |
| `TOPICS` | 议题关键词列表 | 算法推荐、平台治理、数字新闻、情感传播 |
| `RESULT_COUNT` | 每天推送篇数 | 3 |
| `POOL_SIZE` | 每次检索拉取条数 | 60 |
| `WINDOW_DAYS_TIERS` | 时间窗阶梯（自动放宽） | 30 / 90 / 365 / 不限 |

---

## ❓ 常见问题

**Q：收不到邮件？**
检查垃圾邮件箱；确认 `.env` 里的 QQ 授权码正确、且已在邮箱设置中开启 SMTP 服务。

**Q：检索结果为 0 / 时间窗被放宽到 365 天？**
目标期刊多为月刊/双月刊，且知网收录有延迟，近期文章本就少。可**增加期刊或关键词**扩大候选池。

**Q：提示密钥为空 / DeepSeek 调用失败？**
确认 `.env` 三个变量都填了，且 DeepSeek 账户有余额。

**Q：中文乱码？**
脚本已强制以 UTF-8 调用 `cnki-mcp` 并兼容 GBK 解码。若仍乱码，请确认终端编码为 UTF-8。

---

## ⚠️ 已知限制

- **无法获取被引次数**：知网接口返回的被引数为空，故无法显示「被引 N 次」，也无法做「被引最高」的精确筛选
- **时间窗可能放宽**：受收录延迟影响，「近 30 天」可能凑不够 3 篇，脚本会自动放宽
- **依赖上游 cnki-mcp**：检索能力与稳定性受上游项目限制

---

## 🔒 安全说明

- `.env` 已加入 `.gitignore`，**不会上传到 Git**
- 请勿将真实密钥提交到仓库；换电脑时参考 `.env.example` 重建 `.env`
- 密钥一旦泄露，请立即到对应平台重新生成

---

## 📄 免责声明

- 本项目仅为**个人学习**用途
- 与中国知网（CNKI）无任何所属关系
- 请勿用于批量爬取、非法获取论文等违规行为
- 使用者自行承担使用本项目产生的一切后果

---

## 🙏 致谢

- 数据检索能力来自开源项目 [`cnki-mcp`](https://github.com/SepineTam/cnki-mcp)，感谢原作者
- 智能筛选与推荐理由由 [DeepSeek](https://www.deepseek.com/) 提供

---

## 📜 License

本项目基于上游 `cnki-mcp` 的许可证发布，请一并遵守其条款。
详见仓库中的 `LICENSE` 文件。