# OASIS 舆论推演平台

> 研究课题：基于OASIS多智能体仿真的推荐算法对娱乐事件舆论失衡影响研究
> 事件：2026年2月27日—4月8日中美伊冲突舆论分析

---

## 项目结构

```
project/
├── index.html              ← 前端演示页面（粒子力导向网络可视化）
├── main.py                 ← FastAPI 后端 API
├── oasis_local_runner.py   ← 本地 OASIS 仿真运行器
├── requirements.txt        ← Python 依赖
├── .env                    ← 环境配置文件
└── oasis_model/            ← OASIS 框架源码
```

---

## 使用流程

### 第一步：启动 Ollama 服务

1. 打开命令提示符（CMD）或 PowerShell
2. 运行以下命令启动 Ollama：
   ```bash
   ollama serve
   ```
3. 确保已下载模型（如未下载，运行）：
   ```bash
   ollama pull qwen2.5:3b
   ```

**验证 Ollama 是否运行：**
```bash
curl http://127.0.0.1:11434/api/tags
```

---

### 第二步：启动后端服务

1. 打开**另一个**命令提示符窗口
2. 进入项目目录：
   ```bash
   cd d:\oasis\files
   ```
3. 启动后端服务：
   ```bash
   .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

**简化启动命令（如果已在项目目录）：**
```bash
.venv\Scripts\python -m uvicorn main:app
```

4. 看到以下信息表示启动成功：
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```

**验证后端是否运行：**
```bash
curl http://127.0.0.1:8000/health
```

---

### 第三步：打开前端页面

1. 打开浏览器（Chrome/Edge/Firefox）
2. 在地址栏输入：
   ```
   http://127.0.0.1:8000/
   ```
3. **⚠️ 重要：** 不要通过 IDE（如 PyCharm）直接打开 `index.html` 文件，否则会出现 "Failed to fetch" 错误

---

### 第四步：使用舆情分析

| 功能 | 操作 |
|------|------|
| **选择事件** | 点击左侧事件列表中的美伊冲突事件 |
| **启动仿真** | 配置参数后点击「▶ 启动网络仿真」 |
| **自定义分析** | 在底部输入事件标题和内容，点击「分析自定义文本」 |

---

## 关闭服务

### 关闭后端服务

在运行后端服务的命令窗口中，按：
```
Ctrl + C
```
然后按 `Y` 确认。

**或者：**
- 直接关闭命令窗口
- 或通过任务管理器结束 Python/uvicorn 进程

### 关闭 Ollama 服务

在运行 Ollama 的命令窗口中，按：
```
Ctrl + C
```

---

## 窗口状态检查

正常运行时应该有 **2-3 个窗口**：

| 窗口 | 状态 |
|------|------|
| Ollama 服务 | `ollama serve` 运行中 |
| 后端服务 | `Uvicorn running on http://0.0.0.0:8000` |
| 浏览器 | 打开 `http://127.0.0.1:8000/` |

---

## 常见问题

### Q: 显示 "Failed to fetch"
- 检查后端服务是否启动
- 确认浏览器地址是 `http://127.0.0.1:8000/` 而不是 `localhost:63342`
- 不要通过 IDE 直接打开 `index.html`

### Q: 显示 "Ollama 连接失败"
- 检查 `ollama serve` 是否运行
- 检查 `http://127.0.0.1:11434` 是否可访问

### Q: 端口被占用
如果 8000 端口被占用，可以更换端口：
```bash
.venv\Scripts\python -m uvicorn main:app --port 8080
```
然后访问 `http://127.0.0.1:8080/`

---

## 快速启动（完整版）

### 安装依赖

```bash
cd d:\oasis\files
pip install -r requirements.txt
```

### 启动服务

**终端 1 - 启动 Ollama：**
```bash
ollama serve
```

**终端 2 - 启动后端：**
```bash
cd d:\oasis\files
.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**浏览器访问：**
```
http://127.0.0.1:8000/
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
| POST | `/analysis/text` | 分析自定义文本 |
| GET  | `/analytics/overview` | 整体舆情概览 |
| GET  | `/agents/profiles` | Agent角色配置 |
| GET  | `/health` | 服务健康检查 |

---

## 仿真参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `event_id` | 事件ID（evt_0227 ~ evt_0408） | 必填 |
| `agent_count` | 智能体数量 | 200 |
| `activation_prob` | 每步激活概率 | 0.3 |
| `steps` | 仿真步数 | 20 |
| `rec_algorithm` | 推荐算法：interest/hot_score/mixed | mixed |
| `llm_model` | LLM模型 | qwen2.5:3b |

---

## 调用示例

```bash
# 1. 查看事件列表
curl http://localhost:8000/events

# 2. 启动仿真
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_0227",
    "agent_count": 200,
    "activation_prob": 0.3,
    "steps": 20,
    "rec_algorithm": "mixed",
    "llm_model": "qwen2.5:3b"
  }'

# 3. 查询结果（替换simulation_id）
curl http://localhost:8000/simulate/sim_xxxxxxxx

# 4. 分析自定义文本
curl -X POST http://localhost:8000/analysis/text \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试事件",
    "content": "事件描述内容",
    "llm_model": "qwen2.5:3b"
  }'

# 5. 整体舆情概览
curl http://localhost:8000/analytics/overview
```

---

## OASIS 核心模块说明

### Agent 类型分布
| 类型 | 比例 | 初始立场 | 影响力 |
|------|------|----------|--------|
| 官方媒体 | 10% | 偏正向 | 高 |
| 意见领袖KOL | 15% | 全范围 | 中高 |
| 普通民众 | 60% | 按事件基线分布 | 低 |
| 学者专家 | 15% | 趋中立 | 中 |

### 推荐算法影响
- **interest**：兴趣推荐 → 信息茧房最强
- **hot_score**：热度推荐 → 加速情绪传播
- **mixed**：混合推荐 → 抑制极化

---

## 环境配置

如需修改配置，编辑 `.env` 文件：

```bash
# Ollama 配置
OLLAMA_BASE_URL=http://127.0.0.1:11434
OASIS_LOCAL_MODEL=qwen2.5:3b

# 本地 Python 环境（可选）
LOCAL_OASIS_PYTHON=
```

---

## 技术栈

- **前端**：原生 HTML + CSS + JavaScript（粒子力导向网络可视化）
- **后端**：FastAPI + Python
- **AI 模型**：本地 Ollama (qwen2.5:3b)
- **仿真框架**：CAMEL-AI OASIS
