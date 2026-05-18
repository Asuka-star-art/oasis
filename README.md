# OASIS 舆论推演平台

> 研究课题：基于OASIS多智能体仿真的推荐算法对娱乐事件舆论失衡影响研究  
> 事件：2026年2月27日—4月8日中美伊冲突舆论分析

---

## 项目结构

```
project/
├── index.html              ← 前端演示页面（直接浏览器打开）
└── backend/
    ├── main.py             ← FastAPI 后端 API
    └── requirements.txt    ← Python 依赖
```

---

## 快速启动

### 前端
直接用浏览器打开 `index.html` 即可，无需任何安装。

### 后端 API

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn main:app --reload --port 8000

# 访问交互文档
open http://localhost:8000/docs
```

---

## API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/events` | 获取所有事件列表 |
| GET  | `/events/{event_id}` | 获取事件详情 |
| POST | `/simulate` | 启动仿真任务 |
| GET  | `/simulate/{id}` | 查询仿真进度/结果 |
| GET  | `/simulate/{id}/stream` | SSE实时推送进度 |
| POST | `/analyze/recommendation-bias` | 三算法对比分析 |
| GET  | `/analytics/overview` | 整体舆情概览 |
| GET  | `/agents/profiles` | Agent角色配置 |
| GET  | `/health` | 服务健康检查 |

---

## 仿真参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `event_id` | 事件ID（evt_0227 ~ evt_0408） | 必填 |
| `agent_count` | 智能体数量 | 1000 |
| `activation_prob` | 每步激活概率 | 0.3 |
| `steps` | 仿真步数 | 40 |
| `rec_algorithm` | 推荐算法：interest/hot_score/mixed | mixed |
| `llm_model` | LLM模型 | claude-sonnet-4-5 |

---

## 调用示例

```bash
# 1. 查看事件列表
curl http://localhost:8000/events

# 2. 启动仿真
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_0322",
    "agent_count": 1000,
    "activation_prob": 0.3,
    "steps": 40,
    "rec_algorithm": "interest",
    "llm_model": "claude-sonnet-4-5"
  }'

# 3. 查询结果（替换simulation_id）
curl http://localhost:8000/simulate/sim_xxxxxxxx

# 4. 三算法对比
curl -X POST "http://localhost:8000/analyze/recommendation-bias?event_id=evt_0322&agent_count=500&steps=30"

# 5. 整体舆情概览
curl http://localhost:8000/analytics/overview
```

---

## OASIS 核心模块说明

### Agent 类型分布
| 类型 | 比例 | 初始立场 | 影响力 |
|------|------|----------|--------|
| 官方媒体 | 5% | 偏正向 (0.4~1.0) | 高 (20~100) |
| 意见领袖KOL | 10% | 全范围 | 中高 (10~60) |
| 普通民众 | 65% | 按事件基线分布 | 低 (0.5~3) |
| 学者专家 | 10% | 趋中立 (-0.5~0.5) | 中 (5~25) |
| 海外华人 | 10% | 偏反对 (-0.8~0.4) | 低 (1~10) |

### 推荐算法影响
- **兴趣推荐**：按立场相似度推荐 → 信息茧房最强，极化放大约34%
- **热度推荐**：按热度分数推荐 → 加速情绪内容传播，极化放大约19%
- **混合推荐**：引入多样性 → 抑制极化约12%

### 立场更新公式
```
新立场 = 内容影响 × 0.4 + 社会影响 × 0.3 + 原始立场 × 0.3
```
超过极化阈值时，极端立场被进一步强化（×1.1）。

---

## 云端 OASIS API 接入

当前版本已改为“本地前后端 + 云端 OASIS API 代理”模式：

- 前端事件列表、模型列表、分析结果全部通过接口获取。
- 后端不再使用本地随机仿真作为主流程，而是调用云端 OASIS 模型。
- 支持研究事件库分析，也支持直接提交自定义娱乐事件文本。

启动前请配置环境变量：

```bash
# 必填
OASIS_API_BASE_URL=https://your-oasis-api-host
OASIS_API_KEY=your_api_key

# 可选，默认 custom
OASIS_API_STYLE=custom
OASIS_ANALYZE_PATH=/v1/analyze
OASIS_MODELS_PATH=/v1/models

# 如果你的云端接口兼容 OpenAI chat completions
OASIS_API_STYLE=openai_compatible
OASIS_CHAT_PATH=/v1/chat/completions
```

更直接的做法：

1. 复制 `.env.example` 为 `.env`
2. 在 `.env` 里填写你的云端 URL 和 KEY

示例：

```bash
OASIS_API_BASE_URL=https://your-oasis-api-host
OASIS_API_KEY=your_api_key
```

核心接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/models` | 获取云端可用模型 |
| POST | `/simulate` | 分析事件库中的事件 |
| POST | `/analysis/text` | 分析自定义娱乐事件文本 |
| GET | `/simulate/{id}` | 查询分析进度和结果 |
| GET | `/health` | 查看服务和云端配置状态 |

本地启动：

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

访问地址：

- 前端页面：`http://127.0.0.1:8000/`
- 接口文档：`http://127.0.0.1:8000/docs`
