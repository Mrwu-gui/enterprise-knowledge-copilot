# LOK 企业知识 Agent 平台

这是一个从母版源码导出企业版和服务商版的交付项目。

当前仓库不是两套独立代码，而是一套母版源码，通过 `backend/release_profiles.py` 按版本裁剪成：

- `enterprise`：企业版，单后台
- `service_provider`：服务商版，平台后台 + 租户后台

## 当前要看什么

- 文档入口：`docs/README.md`
- 版本拆分规则：`backend/release_profiles.py`
- 导出脚本：`scripts/export_all_releases.py`
- 最新导出目录：
  - `output/releases/lok_enterprise/`
  - `output/releases/lok_service_provider/`

## 一键导出

```bash
python3 scripts/export_all_releases.py
```

导出完成后会得到：

```text
question
  -> guardrails
  -> cache lookup
  -> query rewrite
  -> entity alias expansion
  -> query profile classification
  -> answer strategy routing
  -> tool-first / knowledge-rag / general-fallback / realtime-fallback
  -> retrieval backend selection
  -> bm25 / qdrant / hybrid
  -> rerank
  -> prompt build
  -> llm generation
  -> cache write + chat log + retrieval trace
```

## 问题路由示例

| 问题类型 | 示例 | 回答策略 | 检索方式 |
|---|---|---|---|
| 流程 / 制度问题 | `合同审批规范是什么` | `knowledge_rag` | `hybrid` |
| 时间 / 工具类问题 | `今天周几了` | `tool_first` | 工具直达 |
| 实时类问题 | `最近有哪些网络维护公告` | `realtime_fallback` | 检索优先，低命中再 fallback |
| 通用解释问题 | `RAG 是什么` | `general_fallback` | 检索 + 模型兜底 |

## 技术栈

### 后端

- Python
- FastAPI
- LangGraph
- SQLite
- Qdrant
- NumPy / scikit-learn
- Jieba

### 前端

- HTML
- TailwindCSS
- Vanilla JavaScript
- SSE 流式渲染

### AI / 检索

- BM25
- Vector Retrieval
- Hybrid Fusion
- Rerank
- Prompt Routing
- Session Memory

## 项目结构

```text
backend/
  main.py                    # FastAPI 入口
  chat_workflow.py           # LangGraph 聊天编排
  rag.py                     # RAG 引擎与运行时构建
  retrievers.py              # BM25 / Qdrant / Hybrid 检索器
  rerankers.py               # 本地与远程重排器
  retrieval_orchestration.py # query 路由 / 改写 / 重试 / judge
  document_processing.py     # 文档解析与语义切片
  llm_service.py             # 模型路由 / fallback / 流式生成
  database.py                # 账号、日志、会话、聊天存储
  tools.py                   # weather / datetime / email 工具路由

frontend/
  admin_v2.html              # 平台后台
  tenant_v2.html             # 租户后台
  index_v2.html              # 前台聊天页
  login_v2.html              # 登录页

data/
  app_config.json
  retrieval_config.json
  tenants/

knowledge/
  permanent/
  seasonal/
  hotfix/
```

## 工程化亮点

### 检索编排

- 问题画像分类：`identifier_lookup / keyword_exact / faq_semantic / process_policy`
- 企业名、系统名、缩写、别名扩召回
- 分阶段检索重试
- 检索质量判断与置信度分层

### 可解释性

- 统一 `knowledge_hits`
- 统一 `retrieval_trace`
- 检索摘要卡
- 命中文件卡
- 证据片段卡
- 请求日志与对话日志联动追踪

### 企业级能力

- 多租户隔离
- Prompt 定制
- 本地 / 远程检索配置切换
- 本地 / 远程 Rerank 切换
- 模型主备配置
- Key 池轮换

### 产品化能力

- 平台后台 + 租户后台 + 前台聊天三端
- no-cache 模板下发，避免前端吃旧页面
- 企业登录页与品牌化主题能力
- 类 Chat 产品的会话列表与多轮记忆
- `output/releases/lok_enterprise/`
- `output/releases/lok_service_provider/`
- `output/releases/lok_enterprise_latest.zip`
- `output/releases/lok_service_provider_latest.zip`

## 本地启动

```bash
pip install -r requirements.txt
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 6090 --reload
```

## 当前文档集合

- `docs/00_版本与交付说明.md`
- `docs/01_功能介绍.md`
- `docs/02_部署与启动.md`
- `docs/03_使用教程.md`
- `docs/04_二开与接口说明.md`
- `docs/05_运维排障.md`
