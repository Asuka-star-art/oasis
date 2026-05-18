from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import asyncio

# Load .env
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OASIS_DB_PATH = os.getenv("OASIS_DB_PATH", "./data/reddit_simulation.db")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "qwen-2.5-7b")

# Ensure DB path env is visible to oasis/examples
os.environ["OASIS_DB_PATH"] = OASIS_DB_PATH

# Lazy imports for model libraries
from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import AgentGraph, SocialAgent, UserInfo

app = FastAPI(title="OASIS舆情分析服务")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
from fastapi.responses import HTMLResponse

# Serve a minimal frontend at /
@app.get("/", response_class=HTMLResponse)
async def root():
    html = """<!doctype html>
<html lang=\"zh-CN\"> 
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>OASIS 舆情分析</title>
  <style>body{font-family:Arial,Helvetica,sans-serif;margin:24px}textarea{width:100%;height:160px}button{padding:8px 16px;margin-top:8px}pre{background:#f6f6f6;padding:12px}</style>
</head>
<body>
  <h1>OASIS 舆情分析</h1>
  <p>输入要分析的文本，点击“分析”。</p>
  <textarea id=\"text\">示例：某产品负面消息在社交媒体传播，引发大量投诉，需快速响应。</textarea>
  <br>
  <button id=\"btn\">分析</button>
  <h2>运行信息</h2>
  <div id=\"info\">正在检测服务状态...</div>
  <h2>结果</h2>
  <pre id=\"result\">等待分析结果...</pre>

  <script>
    // 查询 health 显示模式
    async function updateInfo(){
      try{
        const r = await fetch('/health');
        const j = await r.json();
        const mode = j.cloud_mode ? '云端 OASIS API 模式' : '本地 Ollama 模型模式';
        document.getElementById('info').textContent = `状态: ${j.status}；模式: ${mode}`;
      }catch(e){
        document.getElementById('info').textContent = '无法获取服务状态: '+e;
      }
    }
    updateInfo();

    document.getElementById('btn').addEventListener('click', async ()=>{
      const text = document.getElementById('text').value;
      document.getElementById('result').textContent = '正在分析...';
      try{
        const resp = await fetch('/analyze', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({text})
        });
        const data = await resp.json();
        document.getElementById('result').textContent = JSON.stringify(data, null, 2);
      }catch(e){
        document.getElementById('result').textContent = '请求失败: '+e;
      }
    });
  </script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


class Item(BaseModel):
    text: str

# Initialize model and agent on startup
@app.on_event("startup")
async def startup_event():
    # Check if cloud OASIS API is configured; if so, use cloud mode and skip local model init
    app.state.OASIS_API_BASE_URL = os.getenv("OASIS_API_BASE_URL", "").strip()
    app.state.OASIS_API_KEY = os.getenv("OASIS_API_KEY", "").strip()
    if app.state.OASIS_API_BASE_URL and app.state.OASIS_API_KEY:
        app.state.cloud_mode = True
        # normalize base url
        app.state.OASIS_API_BASE_URL = app.state.OASIS_API_BASE_URL.rstrip('/')
        app.state.agent = None
        app.state.model = None
        app.state.agent_graph = None
        return

    app.state.cloud_mode = False
    # Create model backend (Ollama)
    try:
        app.state.model = ModelFactory.create(
            model_platform=ModelPlatformType.OLLAMA,
            model_type=OLLAMA_MODEL_NAME,
            url=OLLAMA_BASE_URL,
        )
    except Exception as e:
        # model creation failure will be visible in logs; re-raise to fail startup
        raise RuntimeError(f"Failed to create model backend: {e}")

    # Create agent graph and social agent
    app.state.agent_graph = AgentGraph()
    user_info = UserInfo(user_name="analyst_agent", name="Analyst",
                         description="舆情分析专用agent", profile=None,
                         recsys_type="reddit")
    app.state.agent = SocialAgent(
        agent_id=0,
        user_info=user_info,
        agent_graph=app.state.agent_graph,
        model=app.state.model,
        available_actions=None,
    )

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cloud_mode": getattr(app.state, "cloud_mode", False),
        "oasis_api_base": (getattr(app.state, "OASIS_API_BASE_URL", None) is not None)
    }

import httpx

@app.post("/analyze")
async def analyze(item: Item):
    # If cloud mode is enabled, forward request to remote OASIS API
    if getattr(app.state, "cloud_mode", False):
        base = app.state.OASIS_API_BASE_URL
        api_key = app.state.OASIS_API_KEY
        url = f"{base}/analyze"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"text": item.text}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": f"Cloud API request failed: {e}"}

    # Local mode: use agent to analyze
    prompt = (
        "请对以下文本做舆情分析：\n\n"
        f"{item.text}\n\n"
        "请输出：情感倾向（正/中/负）、主要观点、关键关键词、简短应对建议。"
    )
    agent = app.state.agent
    if agent is None:
        return {"error": "分析器未初始化（本地模型/agent 未启用）"}
    # Perform interview (uses model to answer)
    res = await agent.perform_interview(prompt)
    content = res.get("content") if isinstance(res, dict) else str(res)
    return {"analysis": content}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
