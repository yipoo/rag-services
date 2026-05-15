# RAG Services — 多租户多行业智能客服知识库

Phase 0 + Phase 1 MVP。一套基于本地知识库 + 本地 Ollama 大模型的客服智能问答系统，多租户、多行业从架构第一行代码就支持。

## 架构概览

```
┌──────────────┐   HTTP/REST   ┌────────────────────────┐
│ React 后台   │ ────────────► │  FastAPI 后端          │
│ (5173 端口)  │               │  (8000 端口)           │
└──────────────┘               │                        │
                               │  ├─ 租户/行业上下文     │
                               │  ├─ 知识库管理         │
                               │  ├─ 文档异步处理流水线  │
                               │  ├─ RAG 检索           │
                               │  └─ LLM 网关 (Ollama)  │
                               └────┬───────┬───────────┘
                                    │       │
                ┌───────────────────┘       └──────────┐
                ▼                                       ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐
         │ Postgres │  │  Qdrant  │  │  MinIO   │  │  Ollama     │
         │ (元数据) │  │ (向量库) │  │ (文件)   │  │ (本地 LLM)  │
         └──────────┘  └──────────┘  └──────────┘  └─────────────┘
```

## 已实现的功能

✅ 多租户 + 多行业的数据模型（每条知识、每条对话都带 `tenant_id` + `industry_code`）
✅ 平台公共知识库（`tenant_id=0`）+ 租户私有知识库
✅ 行业级订阅（一个租户可订阅多个行业）
✅ JWT 鉴权 + 平台管理员/租户管理员角色
✅ 知识集 (Knowledge Set) CRUD
✅ 文档：文件上传 / URL 抓取 / 手动录入
✅ 异步解析（PDF / Word / TXT / Markdown / HTML）
✅ 自动切分 → 本地 embedding (bge-small-zh) → Qdrant 索引
✅ 检索范围自动限定到 `(tenant + industry, PLATFORM + industry)`
✅ 调用本地 Ollama 大模型生成答案 + 引用片段 + 置信度 + 转人工建议
✅ 调试器页面（实时看检索结果 + 答案）

## 快速启动

### 前置依赖
- Python 3.11+
- Node.js 18+
- Docker Desktop（启动）
- Ollama（本地启动，并提前拉取 `deepseek-r1:7b`）

### 步骤

```bash
# 1. 启动基础设施（Postgres / Redis / Qdrant / MinIO）
docker compose up -d

# 2. 后端
cd backend
cp .env.example .env
# 确认 .env 里的 LLM_BASE_URL 和 LLM_MODEL 指向本地 Ollama

python3.11 -m venv .venv
.venv/bin/pip install -e .

# (推荐) 一次性把 embedding/rerank 模型拉到本地缓存，省得后面每次启动等下载
PYTHONPATH=. .venv/bin/python scripts/preload_models.py

# 启动（首次启动会自动建表 + 创建 admin 用户 + 种子行业 + demo 租户）
.venv/bin/uvicorn app.main:app --reload --port 8000

# 3. 前端（新开一个 terminal）
cd frontend
npm install
npm run dev
```

访问：
- 后台：http://localhost:5173
- API 文档：http://localhost:8000/docs
- MinIO Console：http://localhost:9001 （minioadmin/minioadmin）
- Qdrant Dashboard：http://localhost:6333/dashboard

### 默认账号

```
邮箱: admin@example.com
密码: admin123456
```

第一次登录后会看到 demo 租户，订阅了 `general / education / catering` 三个行业。

## 试用流程

1. **登录** → 顶部自动选中 demo 租户
2. **切换行业**（顶部"行业"下拉框）→ 例如选 `education`
3. **知识库 → 知识集** → 新建一个"退费政策"知识集
4. **知识库 → 文档** → "手动录入"，写一段退费政策
5. 等几秒，状态从 `parsing` 变成 `published`，切片数 > 0
6. **对话调试** → 输入"可以退费吗？" → 看到回答 + 右侧召回的知识片段
7. **切换到 catering 行业** → 之前的知识不会被检索到（**行业隔离生效**）

## 关键设计点

### 多租户数据隔离
- 所有 KB 表都带 `tenant_id` 和 `industry_code` + 复合索引
- Qdrant 用单 collection + payload 过滤（`tenant_id`, `industry_code` 都建了索引）
- API 强制要求 `X-Tenant-Id` header，依赖注入校验用户是否为该租户成员

### 行业范围解析
请求时 `industry_code` 来源优先级：
1. `X-Industry` header（显式传）
2. 租户 `default_industry_code`
3. 兜底 `general`

### 文档处理流水线
`upload → put MinIO → background task → parse → chunk → embed → upsert Qdrant`
状态：`pending → parsing → published / failed`，失败会写错误信息。

### 模型缓存

所有本地模型（fastembed embedding、sentence-transformers reranker）统一缓存到：

```
~/.cache/rag-services/models/
├── fastembed/              # bge-small-zh-v1.5 (~100MB)
└── huggingface/            # bge-reranker-v2-m3 (~600MB)
```

可通过 `MODEL_CACHE_DIR` 环境变量改路径。一次下载、永久复用，**不再受 CWD 影响**。

### LLM 配置
`backend/.env` 里：
```
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=deepseek-r1:7b
```

## 项目结构

```
backend/
├── app/
│   ├── api/              # HTTP 路由
│   ├── core/             # 配置、DB、鉴权、依赖注入、上下文
│   ├── models/           # SQLAlchemy 模型
│   ├── schemas/          # Pydantic 入参/出参
│   ├── services/         # 业务能力（embedding/Qdrant/LLM/文档处理…）
│   └── main.py           # FastAPI 入口 + 启动 bootstrap
├── scripts/
│   └── smoketest.py      # 端到端验证脚本
├── pyproject.toml
└── .env.example

frontend/
├── src/
│   ├── api/              # axios 封装
│   ├── store/            # zustand 状态
│   ├── components/       # Layout
│   ├── pages/            # 各页面
│   ├── App.tsx           # 路由
│   └── main.tsx
└── package.json

docker-compose.yml        # postgres + redis + qdrant + minio
```

## 测试

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/smoketest.py
```

预期输出：
```
✓ login
✓ me: tenants=['demo']
✓ industries: ['general', 'education', ...]
✓ created knowledge set id=1
✓ created document id=1
✓ document processed: chunks=N
✓ chat: retrieval=N top_score=...
✓ all assertions passed
```

## Roadmap（接下来）

- Phase 2: FAQ 模块、切片手动编辑、文档版本管理、URL 批量抓取
- Phase 3: 对话记录浏览 + 标注 + 一键沉淀 FAQ
- Phase 4: BM25 + 向量混合检索 + Rerank（bge-reranker）
- Phase 5: 客服平台 Adapter（美洽 / 53客服 webhook）
- Phase 6: 转人工状态机、PII 脱敏、审计后台
