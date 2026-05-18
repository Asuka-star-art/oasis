from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

LOCAL_WORKDIR = BASE_DIR / ".oasis_local"
LOCAL_WORKDIR.mkdir(exist_ok=True)


app = FastAPI(
    title="OASIS Local Simulation API",
    description="Locally deployed OASIS framework plus local Ollama LLM for public-opinion simulation.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulationRequest(BaseModel):
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    event_description: Optional[str] = None
    source_platform: str = "微博 / 新闻评论 / 短视频 / 论坛"
    agent_count: int = Field(default=1000, ge=100, le=10000)
    activation_prob: float = Field(default=0.3, ge=0.01, le=1.0)
    steps: int = Field(default=40, ge=10, le=200)
    polarization_threshold: float = Field(default=0.6, ge=0.1, le=1.0)
    rec_algorithm: Literal["interest", "hot_score", "mixed"] = "mixed"
    llm_model: str = os.getenv("OASIS_LOCAL_MODEL", "qwen2.5:3b")


class TextAnalysisRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=10, max_length=6000)
    source_platform: str = "微博 / 新闻评论 / 短视频 / 论坛"
    llm_model: str = os.getenv("OASIS_LOCAL_MODEL", "qwen2.5:3b")
    rec_algorithm: Literal["interest", "hot_score", "mixed"] = "mixed"


EVENTS_DB: dict[str, dict[str, Any]] = {
    "evt_0227": {
        "id": "evt_0227",
        "date": "2026-02-27",
        "title": "美军对伊实施精确打击",
        "description": "美军对伊朗目标实施打击后，国际舆论迅速升温，中国社交平台围绕军事升级、外交应对和地区安全展开激烈讨论。",
        "intensity": 0.91,
        "tags": ["军事行动", "中美关系", "伊朗", "外交"],
        "baseline_pro": 0.45,
        "baseline_anti": 0.25,
        "baseline_neutral": 0.30,
    },
    "evt_0303": {
        "id": "evt_0303",
        "date": "2026-03-03",
        "title": "中国官方媒体集中发声",
        "description": "人民日报、新华社、央视等密集发文，强调地区稳定与外交斡旋，舆论开始围绕官方叙事重新聚集。",
        "intensity": 0.72,
        "tags": ["官方媒体", "舆论引导", "外交立场"],
        "baseline_pro": 0.55,
        "baseline_anti": 0.20,
        "baseline_neutral": 0.25,
    },
    "evt_0308": {
        "id": "evt_0308",
        "date": "2026-03-08",
        "title": "伊朗宣布暂停相关谈判",
        "description": "伊朗宣布暂停与美方相关议题谈判，局势进一步升级，国内舆论对冲突走向出现更明显分化。",
        "intensity": 0.86,
        "tags": ["谈判中止", "外交危机", "局势升级"],
        "baseline_pro": 0.50,
        "baseline_anti": 0.22,
        "baseline_neutral": 0.28,
    },
    "evt_0315": {
        "id": "evt_0315",
        "date": "2026-03-15",
        "title": "中美外长紧急通话",
        "description": "中美外长就局势发展进行紧急沟通，外交降温叙事增强，但对美方意图的怀疑仍在传播。",
        "intensity": 0.53,
        "tags": ["外交接触", "中美对话"],
        "baseline_pro": 0.42,
        "baseline_anti": 0.28,
        "baseline_neutral": 0.30,
    },
    "evt_0322": {
        "id": "evt_0322",
        "date": "2026-03-22",
        "title": "国内中东局势热搜爆发",
        "description": "相关话题热度急剧攀升，平台推荐位放大情绪化内容，支持、反对与阴谋论内容同步扩散。",
        "intensity": 0.96,
        "tags": ["热搜", "舆情峰值", "极化"],
        "baseline_pro": 0.60,
        "baseline_anti": 0.18,
        "baseline_neutral": 0.22,
    },
    "evt_0330": {
        "id": "evt_0330",
        "date": "2026-03-30",
        "title": "中国提出三方停火倡议",
        "description": "中国提出中美伊三方停火倡议后，支持外交斡旋的内容增加，但对倡议实际效果的质疑仍然存在。",
        "intensity": 0.62,
        "tags": ["停火倡议", "外交行动", "联合国"],
        "baseline_pro": 0.48,
        "baseline_anti": 0.25,
        "baseline_neutral": 0.27,
    },
    "evt_0405": {
        "id": "evt_0405",
        "date": "2026-04-05",
        "title": "美伊达成临时协议",
        "description": "美伊在多方斡旋下达成临时安排，舆论情绪逐步降温，但此前形成的立场分层仍未完全消退。",
        "intensity": 0.36,
        "tags": ["临时协议", "局势降温", "外交成果"],
        "baseline_pro": 0.35,
        "baseline_anti": 0.32,
        "baseline_neutral": 0.33,
    },
    "evt_0408": {
        "id": "evt_0408",
        "date": "2026-04-08",
        "title": "舆情复盘与总结",
        "description": "对 2026-02-27 至 2026-04-08 周期内的中美伊冲突舆情进行系统复盘，评估推荐算法对失衡扩散的影响。",
        "intensity": 0.22,
        "tags": ["复盘", "总结", "模型分析"],
        "baseline_pro": 0.33,
        "baseline_anti": 0.34,
        "baseline_neutral": 0.33,
    },
}

AGENT_PROFILES = [
    {"type": "media", "description": "官方媒体与门户媒体", "initial_stance_range": [-0.2, 0.9], "influence_range": [20, 100], "proportion": "8%"},
    {"type": "kol", "description": "时政 KOL", "initial_stance_range": [-1.0, 1.0], "influence_range": [10, 80], "proportion": "12%"},
    {"type": "civilian", "description": "普通网民", "initial_stance_range": [-1.0, 1.0], "influence_range": [1, 8], "proportion": "60%"},
    {"type": "scholar", "description": "学者与评论员", "initial_stance_range": [-0.6, 0.6], "influence_range": [5, 30], "proportion": "10%"},
    {"type": "brand", "description": "平台与机构账号", "initial_stance_range": [-0.3, 0.7], "influence_range": [10, 60], "proportion": "10%"},
]

simulations: dict[str, dict[str, Any]] = {}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_distribution(distribution: dict[str, Any]) -> dict[str, float]:
    pro = float(distribution.get("pro", 0.34))
    anti = float(distribution.get("anti", 0.33))
    neutral = float(distribution.get("neutral", 0.33))
    total = pro + anti + neutral
    if total <= 0:
        return {"pro": 0.34, "anti": 0.33, "neutral": 0.33}
    return {
        "pro": round(pro / total, 3),
        "anti": round(anti / total, 3),
        "neutral": round(neutral / total, 3),
    }


def default_bias(rec_algorithm: str) -> dict[str, float]:
    bias_scores = {
        "interest": {"pro_bias": 0.34, "echo_amplify": 0.42, "polarization_contribution": 0.65},
        "hot_score": {"pro_bias": 0.19, "echo_amplify": 0.28, "polarization_contribution": 0.45},
        "mixed": {"pro_bias": 0.12, "echo_amplify": 0.15, "polarization_contribution": 0.28},
    }
    return bias_scores.get(rec_algorithm, bias_scores["mixed"])


def default_key_posts(event: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"author_type": "media", "action": "发帖", "content": f"围绕“{event['title']}”的话题持续冲榜，平台推荐位正在放大冲突情绪与站队内容。"},
        {"author_type": "kol", "action": "转发", "content": "核心账号开始集中转发立场鲜明内容，讨论迅速从事件事实扩散到身份认同对立。"},
        {"author_type": "civilian", "action": "评论", "content": "普通用户逐渐脱离细节分析，更多依据平台高热推荐内容进行判断和表态。"},
    ]


def derive_timeline(result: dict[str, Any], request: SimulationRequest, event: dict[str, Any]) -> list[dict[str, Any]]:
    existing = result.get("timeline_metrics")
    if isinstance(existing, list) and existing:
        return existing

    stance = normalize_distribution(result.get("stance_distribution", {}))
    final_polar = clamp(float(result.get("final_polarization_index", event.get("intensity", 0.7) * 0.75)))
    final_imbalance = clamp(float(result.get("final_imbalance_score", abs(stance["pro"] - stance["anti"]))))
    final_echo = clamp(float(result.get("echo_chamber_index", 0.45)))
    final_herd = clamp(float(result.get("herd_effect_intensity", 0.38)))
    sample_points = min(10, max(8, request.steps // 4))
    timeline: list[dict[str, Any]] = []

    for idx in range(sample_points):
        progress = (idx + 1) / sample_points
        polar = clamp(final_polar * (0.42 + progress * 0.72 - 0.14 * progress * progress))
        imbalance = clamp(final_imbalance * (0.45 + progress * 0.60))
        echo = clamp(final_echo * (0.52 + progress * 0.58))
        herd = clamp(final_herd * (0.55 + progress * 0.55))
        step = max(1, round(request.steps * progress))
        speed = int((request.agent_count * request.activation_prob) * (0.55 + progress * event.get("intensity", 0.7)))
        pro = clamp(stance["pro"] * (0.88 + progress * 0.15))
        anti = clamp(stance["anti"] * (0.90 + progress * 0.12))
        neutral = clamp(1 - pro - anti)
        timeline.append(
            {
                "step": step,
                "activated": max(1, int(request.agent_count * request.activation_prob * (0.7 + progress * 0.25))),
                "new_posts": max(1, int(speed * 0.6)),
                "spread_speed": speed,
                "polarization_index": round(polar, 4),
                "imbalance_score": round(imbalance, 4),
                "herd_effect": round(herd, 4),
                "echo_chamber_index": round(echo, 4),
                "stance_distribution": normalize_distribution({"pro": pro, "anti": anti, "neutral": neutral}),
                "mean_stance": round(pro - anti, 4),
            }
        )
    return timeline


def normalize_result(raw: dict[str, Any], simulation_id: str, request: SimulationRequest, event: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("data", raw)
    stance_distribution = normalize_distribution(payload.get("stance_distribution", {}))
    recommendation_bias = payload.get("recommendation_bias", default_bias(request.rec_algorithm))
    timeline_metrics = derive_timeline(payload, request, event)
    final_polarization = clamp(float(payload.get("final_polarization_index", event.get("intensity", 0.7) * 0.78)))
    final_imbalance = clamp(float(payload.get("final_imbalance_score", abs(stance_distribution["pro"] - stance_distribution["anti"]))))
    echo_chamber_index = clamp(float(payload.get("echo_chamber_index", default_bias(request.rec_algorithm)["echo_amplify"])))
    herd_effect_intensity = clamp(float(payload.get("herd_effect_intensity", 0.35)))
    peak_spread_speed = int(payload.get("peak_spread_speed", max(item["spread_speed"] for item in timeline_metrics)))

    return {
        "simulation_id": simulation_id,
        "event_id": event["id"],
        "event_title": event["title"],
        "rec_algorithm": request.rec_algorithm,
        "llm_model": request.llm_model,
        "total_steps": request.steps,
        "agent_count": request.agent_count,
        "final_polarization_index": round(final_polarization, 4),
        "peak_polarization_index": round(max(item["polarization_index"] for item in timeline_metrics), 4),
        "final_imbalance_score": round(final_imbalance, 4),
        "peak_spread_speed": peak_spread_speed,
        "echo_chamber_index": round(echo_chamber_index, 4),
        "herd_effect_intensity": round(herd_effect_intensity, 4),
        "recommendation_bias": {
            "pro_bias": round(float(recommendation_bias.get("pro_bias", 0.12)), 4),
            "echo_amplify": round(float(recommendation_bias.get("echo_amplify", 0.15)), 4),
            "polarization_contribution": round(float(recommendation_bias.get("polarization_contribution", 0.28)), 4),
        },
        "stance_distribution": stance_distribution,
        "timeline_metrics": timeline_metrics,
        "summary": payload.get(
            "summary",
            f"本地部署的 OASIS 仿真显示，事件“{event['title']}”在 {request.rec_algorithm} 推荐策略下呈现明显舆论分层，极化指数为 {final_polarization:.2f}，失衡度为 {final_imbalance:.2f}。",
        ),
        "key_posts": payload.get("key_posts", default_key_posts(event)),
        "raw_response": raw,
    }


def get_event_payload(request: SimulationRequest) -> dict[str, Any]:
    if request.event_id:
        event = EVENTS_DB.get(request.event_id)
        if not event:
            raise HTTPException(status_code=404, detail=f"事件 {request.event_id} 不存在。")
        return event

    if request.event_title and request.event_description:
        return {
            "id": f"custom_{uuid.uuid4().hex[:8]}",
            "date": datetime.now().date().isoformat(),
            "title": request.event_title,
            "description": request.event_description,
            "intensity": 0.78,
            "tags": ["自定义事件", "冲突舆情"],
            "baseline_pro": 0.4,
            "baseline_anti": 0.35,
            "baseline_neutral": 0.25,
        }

    raise HTTPException(status_code=422, detail="请提供 event_id，或同时提供 event_title 和 event_description。")


class LocalOasisClient:
    def __init__(self) -> None:
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.default_model = os.getenv("OASIS_LOCAL_MODEL", "qwen2.5:3b")
        self.timeout = float(os.getenv("OASIS_LOCAL_TIMEOUT", "900"))
        # 优先使用环境变量指定的 Python，否则使用当前 Python 或 .venv 环境
        custom_python = os.getenv("LOCAL_OASIS_PYTHON", "").strip()
        if custom_python:
            self.python_path = Path(custom_python)
        else:
            # 尝试使用当前 Python 解释器
            self.python_path = Path(sys.executable)
        self.runner_path = BASE_DIR / "oasis_local_runner.py"

    def python_exists(self) -> bool:
        return self.python_path.exists()

    async def ollama_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.ollama_base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        if not await self.ollama_available():
            return [{"id": self.default_model, "label": self.default_model, "provider": "ollama"}]
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.ollama_base_url}/api/tags")
            response.raise_for_status()
            payload = response.json()
        models = []
        for item in payload.get("models", []):
            model_id = item.get("name") or item.get("model")
            if model_id:
                models.append({"id": model_id, "label": model_id, "provider": "ollama"})
        return models or [{"id": self.default_model, "label": self.default_model, "provider": "ollama"}]

    async def analyze(self, request: SimulationRequest, event: dict[str, Any]) -> dict[str, Any]:
        if not self.python_exists():
            raise HTTPException(status_code=503, detail=f"本地 OASIS Python 环境不存在：{self.python_path}")
        if not self.runner_path.exists():
            raise HTTPException(status_code=503, detail=f"本地 OASIS runner 不存在：{self.runner_path}")
        if not await self.ollama_available():
            raise HTTPException(status_code=503, detail=f"Ollama 服务不可用：{self.ollama_base_url}")

        task_id = uuid.uuid4().hex[:12]
        input_path = LOCAL_WORKDIR / f"{task_id}.input.json"
        output_path = LOCAL_WORKDIR / f"{task_id}.output.json"
        payload = {
            "request": request.model_dump(),
            "event": event,
            "ollama_base_url": self.ollama_base_url,
            "model": request.llm_model or self.default_model,
        }
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        process = await asyncio.create_subprocess_exec(
            str(self.python_path),
            str(self.runner_path),
            str(input_path),
            str(output_path),
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"本地 OASIS 仿真失败：{stderr.decode('utf-8', errors='ignore') or stdout.decode('utf-8', errors='ignore')}",
            )
        if not output_path.exists():
            raise HTTPException(status_code=500, detail="本地 OASIS 仿真未生成输出文件。")
        return json.loads(output_path.read_text(encoding="utf-8"))

    async def analyze_text(self, request: TextAnalysisRequest) -> dict[str, Any]:
        sim_request = SimulationRequest(
            event_title=request.title,
            event_description=request.content,
            source_platform=request.source_platform,
            llm_model=request.llm_model,
            rec_algorithm=request.rec_algorithm,
            agent_count=1200,
            steps=40,
            activation_prob=0.3,
            polarization_threshold=0.6,
        )
        event = get_event_payload(sim_request)
        return await self.analyze(sim_request, event)


local_client = LocalOasisClient()


async def run_simulation_task(simulation_id: str, request: SimulationRequest) -> None:
    simulations[simulation_id]["status"] = "running"
    simulations[simulation_id]["progress"] = 5
    event = get_event_payload(request)

    try:
        simulations[simulation_id]["event"] = event
        simulations[simulation_id]["progress"] = 15
        await asyncio.sleep(0.1)

        simulations[simulation_id]["progress"] = 45
        raw = await local_client.analyze(request, event)

        simulations[simulation_id]["progress"] = 85
        result = normalize_result(raw, simulation_id, request, event)

        simulations[simulation_id]["status"] = "completed"
        simulations[simulation_id]["progress"] = 100
        simulations[simulation_id]["result"] = result
        simulations[simulation_id]["current_metrics"] = result["timeline_metrics"][-1]
    except HTTPException as exc:
        simulations[simulation_id]["status"] = "failed"
        simulations[simulation_id]["error"] = exc.detail
    except asyncio.TimeoutError:
        simulations[simulation_id]["status"] = "failed"
        simulations[simulation_id]["error"] = "本地 OASIS 仿真超时。"
    except Exception as exc:  # noqa: BLE001
        simulations[simulation_id]["status"] = "failed"
        simulations[simulation_id]["error"] = str(exc)


def build_overview() -> dict[str, Any]:
    events = list(EVENTS_DB.values())
    total_events = len(events)
    peak_event = max(events, key=lambda item: item["intensity"])
    avg_intensity = sum(item["intensity"] for item in events) / total_events
    return {
        "period": f"{events[0]['date']} ~ {events[-1]['date']}",
        "total_events": total_events,
        "peak_event": peak_event["id"],
        "peak_date": peak_event["date"],
        "overall_metrics": {
            "avg_polarization_index": round(avg_intensity * 0.64, 3),
            "peak_polarization_index": round(peak_event["intensity"] * 0.82, 3),
            "avg_imbalance_score": round(avg_intensity * 0.48, 3),
            "peak_spread_speed": int(1100 * peak_event["intensity"]),
            "total_simulated_posts": int(60000 * avg_intensity),
            "echo_chamber_index": {
                "interest_based": round(avg_intensity * 0.88, 3),
                "hot_score_based": round(avg_intensity * 0.69, 3),
                "mixed": round(avg_intensity * 0.52, 3),
            },
        },
        "stance_evolution": [
            {"date": event["date"], "pro": event["baseline_pro"], "anti": event["baseline_anti"], "neutral": event["baseline_neutral"]}
            for event in events
        ],
        "key_findings": [
            "兴趣型推荐更容易把高情绪、高站队内容持续推向同质用户群。",
            "热度型推荐会显著提高传播速度，但对理性内容的曝光并不稳定。",
            "混合推荐策略能够降低信息茧房强度，更适合冲突议题舆情治理场景。",
        ],
    }


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/index.html", response_class=FileResponse)
async def index_file() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/events")
async def list_events() -> dict[str, Any]:
    return {
        "events": list(EVENTS_DB.values()),
        "period": f"{min(item['date'] for item in EVENTS_DB.values())} ~ {max(item['date'] for item in EVENTS_DB.values())}",
        "total": len(EVENTS_DB),
    }


@app.get("/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    event = EVENTS_DB.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"事件 {event_id} 不存在。")
    return event


@app.get("/models")
async def get_models() -> dict[str, Any]:
    models = await local_client.list_models()
    return {"models": models, "api_style": "local_oasis"}


@app.post("/analysis/text")
async def analyze_text(request: TextAnalysisRequest) -> dict[str, Any]:
    raw = await local_client.analyze_text(request)
    event = {
        "id": f"text_{uuid.uuid4().hex[:8]}",
        "date": datetime.now().date().isoformat(),
        "title": request.title,
        "description": request.content,
        "intensity": 0.75,
        "tags": ["自定义分析", "中美伊冲突"],
    }
    return normalize_result(
        raw=raw,
        simulation_id=f"text_{uuid.uuid4().hex[:10]}",
        request=SimulationRequest(
            event_title=request.title,
            event_description=request.content,
            source_platform=request.source_platform,
            llm_model=request.llm_model,
            rec_algorithm=request.rec_algorithm,
        ),
        event=event,
    )


@app.post("/simulate")
async def start_simulation(request: SimulationRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
    simulations[simulation_id] = {
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "config": request.model_dump(),
        "result": None,
        "error": None,
        "event": None,
    }
    background_tasks.add_task(run_simulation_task, simulation_id, request)
    return {
        "simulation_id": simulation_id,
        "status": "queued",
        "message": "任务已提交，正在调用本地 OASIS + Ollama 仿真。",
        "poll_url": f"/simulate/{simulation_id}",
        "stream_url": f"/simulate/{simulation_id}/stream",
    }


@app.get("/simulate/{simulation_id}")
async def get_simulation_status(simulation_id: str) -> dict[str, Any]:
    sim = simulations.get(simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail="仿真任务不存在。")
    response = {
        "simulation_id": simulation_id,
        "status": sim["status"],
        "progress": sim["progress"],
        "created_at": sim["created_at"],
        "config": sim["config"],
        "event": sim.get("event"),
    }
    if sim.get("current_metrics"):
        response["current_metrics"] = sim["current_metrics"]
    if sim["status"] == "completed":
        response["result"] = sim["result"]
    if sim["status"] == "failed":
        response["error"] = sim["error"]
    return response


@app.get("/simulate/{simulation_id}/stream")
async def stream_simulation(simulation_id: str) -> StreamingResponse:
    if simulation_id not in simulations:
        raise HTTPException(status_code=404, detail="仿真任务不存在。")

    async def event_generator():
        last_progress = -1
        started_at = time.time()
        while time.time() - started_at < 3600:
            sim = simulations.get(simulation_id)
            if not sim:
                break
            if sim["progress"] != last_progress or sim["status"] in {"completed", "failed"}:
                last_progress = sim["progress"]
                payload = {
                    "simulation_id": simulation_id,
                    "status": sim["status"],
                    "progress": sim["progress"],
                    "event": sim.get("event"),
                }
                if sim.get("current_metrics"):
                    payload["metrics"] = sim["current_metrics"]
                if sim["status"] == "completed":
                    payload["result"] = sim["result"]
                if sim["status"] == "failed":
                    payload["error"] = sim["error"]
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if sim["status"] in {"completed", "failed"}:
                    break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/analytics/overview")
async def analytics_overview() -> dict[str, Any]:
    return build_overview()


@app.get("/agents/profiles")
async def get_agent_profiles() -> dict[str, Any]:
    return {
        "agent_types": AGENT_PROFILES,
        "stance_scale": {
            "description": "-1.0（强烈反对） ~ 0（中立） ~ +1.0（强烈支持）",
            "thresholds": {"pro": ">0.3", "anti": "<-0.3", "neutral": "-0.3 ~ 0.3"},
        },
    }


@app.delete("/simulate/{simulation_id}")
async def delete_simulation(simulation_id: str) -> dict[str, str]:
    if simulation_id not in simulations:
        raise HTTPException(status_code=404, detail="仿真任务不存在。")
    del simulations[simulation_id]
    return {"message": f"仿真记录 {simulation_id} 已删除。"}


@app.get("/health")
async def health_check() -> dict[str, Any]:
    ollama_ok = await local_client.ollama_available()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "active_simulations": len(simulations),
        "cloud_api_configured": local_client.python_exists() and ollama_ok,
        "cloud_api_base_url": local_client.ollama_base_url,
        "api_style": "local_oasis",
        "local_oasis_python": str(local_client.python_path),
        "local_oasis_python_exists": local_client.python_exists(),
        "local_oasis_runner": str(local_client.runner_path),
        "ollama_running": ollama_ok,
    }
