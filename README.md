# 📖 个人 AI 阅读助手 (Personal AI Reading Assistant · DeepRead AI)

一个完整可用、面向深度阅读与跨文献研究场景的全栈 Web 应用。支持**网页链接智能抓取 / 文本直接粘贴 / 本地文档上传**，自动提炼**结构化四维摘要**，支持**划词与引用批判性追问**，并提供**多文章「主题」横向对比矩阵与综合报告导出**。

---

## ✨ 功能特性一览

### 1. 核心需求完整实现
- **多源文章导入**：
  - **粘贴文章链接 (URL)**：内置 Readability 风格网页正文抽取器，自动识别标题、作者、站点，剔除导航/脚本/广告噪音；同时支持防反爬备用文本兜底。
  - **直接粘贴长文 / 上传本地 `.txt` & `.md` 文档**：自动完成段落规范化、中英文混合字数统计与预计精读时长测算。
- **四维深度结构化摘要**：
  - **🎯 核心观点 (Core Viewpoints)**：提炼文章核心论断并标注重要度分级（高 / 中）。
  - **⚖️ 关键论据 (Key Arguments & Evidence)**：自动拆解支撑论点、识别论证类型（数据实证 / 典型案例 / 对比反差 / 因果推演）并摘录原文金句。
  - **🧭 作者态度与立场审视 (Author's Stance & Bias)**：评估行文基调、客观度评分（0~100）、目标受众，并主动揭示作者可能存在的**视角局限与隐含假设 (Critical Blindspots)**。
  - **🚀 可行动洞察 (Actionable Insights)**：将文章观点转化为带优先级、适用场景与预期成果的落地行动建议。
- **深度思辨追问 (Interactive Follow-up Q&A)**：
  - 支持围绕当前文章进行多轮追问（如：*“这个观点有什么漏洞？”*、*“和第一性原理有什么关系？”*、*“站在反对者立场如何反驳？”*）。
  - 对话历史按文章独立持久化保存。
- **多文章「主题」横向对比总结 (Topic-Based Multi-Article Synthesis)**：
  - 支持创建任意多个研究「主题」（如：`AI 时代的深度阅读与认知升级`），将多篇不同来源或相反立场的文章归入同一主题。
  - 一键生成跨文献对比综述：**主题全景综述、跨文章核心共识、关键分歧与张力对比、多维横向对比矩阵表格、视角互补路径、综合行动建议**。
- **历史记录与个人知识库管理**：
  - 基于 SQLite + SQLAlchemy 2.0 持久化所有文章、摘要、追问对话与主题报告。
  - 支持**全文关键词搜索**（匹配标题、正文、摘要、标签、批注）、**标签云过滤**、**星标收藏**与**阅读状态流转**（未读 / 精读中 / 已精读）。

### 2. 主动补充的高价值增强功能
1. **🤖 双模 AI 驱动 + Web 界面热配置（开箱 100% 可用）**：
   - **OpenAI 兼容大模型模式**：支持 OpenAI (`gpt-4o-mini` / `gpt-4o`)、DeepSeek (`deepseek-chat`)、通义千问、硅基流动、本地 Ollama 等任意兼容接口。
   - **内置启发式智能分析引擎 (Local Smart Engine)**：未配置 API Key 时自动启用，基于篇章结构特征、论点/论据指示词与跨文档对比算法生成真实针对原文的结构化分析与追问解答，**零外部依赖即可完整运行所有功能**。
   - **运行时动态切换**：无需重启服务，点击右上角 **「⚙️ AI 引擎设置」** 即可在线配置 API Key、切换服务商预设并立即生效。
2. **📌 划词引用追问 & 观点卡片一键质询 (Quote-to-Ask)**：
   - 在「结构化摘要」中点击任意观点/论据旁的 **「💬 引用此观点追问」**，或在「清洗后原文」中用鼠标选中任意段落点击 **「💬 引用选中文字追问」**，即可携带上下文片段发起精准追问。
3. **🧭 主题级跨文章追问 (Topic-Level Multi-Doc Q&A)**：
   - 不仅单篇文章可以追问，切换到「主题对比」视图后，还可以针对主题内的所有文章发起跨文献综合提问。
4. **📝 个人阅读批注 & 📥 一键导出 Markdown 读书笔记 / 主题报告**：
   - 内置个人批注编辑器，支持将「结构化摘要 + 个人批注 + 追问思辨记录」或「多文章主题对比报告」一键导出为排版精美的 `.md` 文件（无缝对接 Obsidian / Notion / Logseq）。
5. **🌱 内置高质量示例文章与对比主题**：
   - 首次启动自动预置 3 篇关于 AI 时代深度阅读与知识工作的深度文章及已生成的主题对比报告，打开浏览器即可零门槛体验完整闭环。

---

## 🏗️ 项目目录结构

```text
ai-reading-assistant/
├── .env.example                 # 环境变量配置模板
├── Dockerfile                   # 生产级容器镜像构建文件
├── docker-compose.yml           # Docker Compose 一键编排配置 (含数据卷持久化与健康检查)
├── requirements.txt             # Python 依赖声明
├── run.py                       # 应用启动入口
├── start.bat / start.sh         # Windows / Linux / macOS 一键启动脚本
├── app/
│   ├── __init__.py              # Flask 应用工厂 (create_app)
│   ├── config.py                # 集中式配置管理
│   ├── database.py              # SQLAlchemy 2.0 数据库引擎与事务上下文管理
│   ├── models.py                # ORM 数据模型 (Article, ArticleMessage, Topic, TopicArticle, TopicMessage, AppSetting)
│   ├── services/                # 核心业务逻辑层 (与 HTTP 层解耦，便于单元测试与扩展)
│   │   ├── scraper_service.py   # 网页正文抓取、噪音剔除与阅读统计服务
│   │   ├── llm_service.py       # AI 双引擎服务 (OpenAI 兼容接口 + 本地启发式智能分析引擎)
│   │   ├── article_service.py   # 文章导入、摘要生成、追问、批注与 Markdown 导出服务
│   │   ├── topic_service.py     # 主题聚合、跨文章对比矩阵生成与主题级追问服务
│   │   └── seed_service.py      # 示例文章与对比主题初始化服务
│   ├── api/                     # RESTful API 路由层
│   │   ├── articles.py          # /api/articles 路由蓝图
│   │   ├── topics.py            # /api/topics 路由蓝图
│   │   └── system.py            # /api/system 路由蓝图 (统计、健康检查、AI 引擎热配置)
│   └── web/                     # 前端视图与静态资源
│       ├── templates/index.html # 三栏式深度阅读与主题研究单页工作台
│       └── static/
│           ├── css/styles.css   # 现代知识库风格响应式样式表
│           └── js/app.js        # 模块化前端状态管理与交互控制
└── tests/                       # Pytest 自动化测试套件
    ├── conftest.py              # 隔离式临时数据库测试夹具
    ├── test_scraper.py          # 网页解析与字数统计单元测试
    ├── test_llm_engine.py       # 摘要、批判性追问与多篇对比引擎测试
    └── test_api.py              # 全链路 REST API 端到端集成测试
```

---

## 🚀 快速启动指南

### 方式一：使用 Docker Compose 启动（推荐生产或跨平台部署）

```bash
# 1. 进入项目目录
cd ai-reading-assistant

# 2. (可选) 复制环境变量文件并按需填入大模型 API Key
cp .env.example .env

# 3. 一键构建并后台启动服务
docker-compose up --build -d

# 4. 浏览器访问
# http://localhost:8000
```
> SQLite 数据库文件会自动持久化挂载在宿主机的 `./data/reading_assistant.db` 目录中，重启容器不会丢失任何阅读记录。

### 方式二：本地 Python 直接启动（开发调试）

确保本地已安装 **Python 3.10+**。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动应用（Windows 可直接双击或运行 start.bat，Linux/macOS 可运行 ./start.sh）
python run.py
```

启动成功后，打开浏览器访问：**http://127.0.0.1:8000**

---

## 🧪 运行自动化测试

项目内置完整的单元测试与端到端 API 集成测试：

```bash
pytest -v
```

---

## 🔌 核心 REST API 接口速览（二次开发指南）

| 模块 | 方法与路径 | 说明 |
| :--- | :--- | :--- |
| **文章管理** | `GET /api/articles` | 查询历史文章（支持 `search`, `tag`, `topic_id`, `favorite`, `status` 参数） |
| **文章导入** | `POST /api/articles` | 导入 URL 或纯文本并自动生成结构化摘要 |
| **文章详情** | `GET /api/articles/<id>` | 获取原文、结构化摘要、个人批注与追问历史 |
| **文章更新** | `PATCH /api/articles/<id>` | 更新个人批注 (`user_notes`)、收藏 (`is_favorite`)、阅读状态 (`reading_status`) |
| **文章追问** | `POST /api/articles/<id>/ask` | 对文章发起追问（支持传入 `question` 与 `quoted_text` 引用片段） |
| **笔记导出** | `GET /api/articles/<id>/export` | 导出单篇结构化读书笔记为 Markdown |
| **主题管理** | `GET / POST /api/topics` | 获取主题列表 / 创建新对比主题 |
| **多篇对比** | `POST /api/topics/<id>/compare` | 对主题下收录的多篇文章生成共识、分歧与横向对比矩阵 |
| **跨篇追问** | `POST /api/topics/<id>/ask` | 针对主题下所有文章发起跨文献追问 |
| **报告导出** | `GET /api/topics/<id>/export` | 导出多文章主题对比综述报告为 Markdown |
| **引擎配置** | `GET / PUT /api/system/llm-config` | 读取或动态更新大模型 API Key、Base URL 与模型名称 |
