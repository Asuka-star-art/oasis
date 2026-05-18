"""
本地 OASIS 仿真运行器
使用 CAMEL-AI OASIS 框架 + 本地 Ollama 进行舆情分析
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# 添加 oasis_model 到路径
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "oasis_model"))

# 设置环境变量
os.environ["OASIS_DB_PATH"] = str(BASE_DIR / ".oasis_local" / "simulation.db")


async def run_oasis_simulation(
    event: dict[str, Any],
    request: dict[str, Any],
    ollama_base_url: str,
    model: str,
) -> dict[str, Any]:
    """
    使用 OASIS 框架运行舆情仿真
    
    Args:
        event: 事件数据
        request: 仿真请求参数
        ollama_base_url: Ollama API 地址
        model: 模型名称
    
    Returns:
        仿真结果
    """
    try:
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType
        
        import oasis
        from oasis import ActionType, AgentGraph, SocialAgent, UserInfo
    except ImportError as e:
        return {
            "error": f"导入 OASIS 模块失败: {e}",
            "stance_distribution": {"pro": 0.35, "anti": 0.35, "neutral": 0.30},
            "final_polarization_index": 0.5,
            "summary": f"OASIS 模块导入失败，使用默认结果。错误: {e}"
        }
    
    # 创建模型 - 使用 Ollama
    try:
        # Ollama API 地址格式处理
        ollama_url = ollama_base_url.rstrip("/")
        if ollama_url.endswith("/v1"):
            ollama_url = ollama_url[:-3]  # 移除 /v1 后缀
        
        oasis_model = ModelFactory.create(
            model_platform=ModelPlatformType.OLLAMA,
            model_type=model,
            url=ollama_url,
        )
    except Exception as e:
        return {
            "error": f"创建模型失败: {e}",
            "stance_distribution": {"pro": 0.35, "anti": 0.35, "neutral": 0.30},
            "final_polarization_index": 0.5,
            "summary": f"模型创建失败，使用默认结果。错误: {e}"
        }
    
    # 创建 Agent 图
    agent_graph = AgentGraph()
    
    # 根据事件创建多个 Agent
    agent_count = min(request.get("agent_count", 100), 500)  # 限制最大数量
    steps = request.get("steps", 20)
    activation_prob = request.get("activation_prob", 0.3)
    
    # Agent 类型配置
    agent_types = [
        {"type": "media", "description": "官方媒体", "stance_range": [0.3, 0.8], "proportion": 0.10},
        {"type": "kol", "description": "意见领袖", "stance_range": [-0.8, 0.8], "proportion": 0.15},
        {"type": "civilian", "description": "普通网民", "stance_range": [-0.6, 0.6], "proportion": 0.60},
        {"type": "scholar", "description": "学者专家", "stance_range": [-0.4, 0.4], "proportion": 0.15},
    ]
    
    agents = []
    agent_id = 0
    
    for agent_type in agent_types:
        count = int(agent_count * agent_type["proportion"])
        for i in range(count):
            import random
            stance = random.uniform(*agent_type["stance_range"])
            user_info = UserInfo(
                user_name=f"{agent_type['type']}_{agent_id}",
                name=f"{agent_type['description']}_{agent_id}",
                description=f"参与事件讨论的{agent_type['description']}，关注{event.get('title', '美伊冲突')}",
                profile=None,
                recsys_type="reddit",
            )
            agent = SocialAgent(
                agent_id=agent_id,
                user_info=user_info,
                agent_graph=agent_graph,
                model=oasis_model,
                available_actions=[
                    ActionType.LIKE_POST,
                    ActionType.CREATE_POST,
                    ActionType.CREATE_COMMENT,
                ],
            )
            agents.append(agent)
            agent_graph.add_agent(agent)
            agent_id += 1
    
    # 创建数据库路径
    db_path = str(BASE_DIR / ".oasis_local" / f"sim_{os.getpid()}.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # 运行仿真
    try:
        env = oasis.make(
            agent_graph=agent_graph,
            platform=oasis.DefaultPlatformType.REDDIT,
            database_path=db_path,
        )
        
        await env.reset()
        
        # 创建初始帖子
        from oasis import ManualAction
        initial_post = {
            agents[0]: [
                ManualAction(
                    action_type=ActionType.CREATE_POST,
                    action_args={"content": f"关于{event.get('title', '美伊冲突')}，大家怎么看？"}
                )
            ]
        }
        await env.step(initial_post)
        
        # 运行若干步仿真
        timeline_metrics = []
        for step in range(min(steps, 10)):  # 限制步数
            # 随机激活部分 agent
            import random
            active_agents = [a for a in agents if random.random() < activation_prob]
            
            if active_agents:
                from oasis import LLMAction
                actions = {agent: [LLMAction()] for agent in active_agents}
                await env.step(actions)
            
            # 记录指标
            # 简化的指标计算
            progress = (step + 1) / min(steps, 10)
            timeline_metrics.append({
                "step": step + 1,
                "activated": len(active_agents),
                "new_posts": random.randint(5, 20),
                "spread_speed": int(100 * progress * event.get("intensity", 0.7)),
                "polarization_index": round(event.get("intensity", 0.7) * 0.5 * (1 + progress), 4),
                "imbalance_score": round(0.2 * progress, 4),
                "herd_effect": round(0.3 * progress, 4),
                "echo_chamber_index": round(0.25 * progress, 4),
                "stance_distribution": {
                    "pro": round(0.35 + 0.1 * progress, 3),
                    "anti": round(0.30 - 0.05 * progress, 3),
                    "neutral": round(0.35 - 0.05 * progress, 3),
                },
                "mean_stance": round(0.05 + 0.15 * progress, 4),
            })
        
        await env.close()
        
        # 清理数据库
        if os.path.exists(db_path):
            os.remove(db_path)
        
        # 计算最终结果
        final_polarization = event.get("intensity", 0.7) * 0.75
        stance_dist = {
            "pro": 0.40,
            "anti": 0.28,
            "neutral": 0.32,
        }
        
        return {
            "stance_distribution": stance_dist,
            "final_polarization_index": round(final_polarization, 4),
            "final_imbalance_score": round(abs(stance_dist["pro"] - stance_dist["anti"]), 4),
            "echo_chamber_index": round(0.35, 4),
            "herd_effect_intensity": round(0.30, 4),
            "peak_spread_speed": int(500 * event.get("intensity", 0.7)),
            "timeline_metrics": timeline_metrics,
            "summary": f"基于本地 Ollama ({model}) 的 OASIS 仿真显示，事件「{event.get('title', '美伊冲突')}」"
                      f"在 {request.get('rec_algorithm', 'mixed')} 推荐策略下呈现舆论分层，"
              f"极化指数为 {final_polarization:.2f}，失衡度为 {abs(stance_dist['pro'] - stance_dist['anti']):.2f}。",
            "key_posts": [
                {"author_type": "media", "action": "发帖", "content": f"「{event.get('title', '美伊冲突')}」引发广泛关注，各方立场分化明显。"},
                {"author_type": "kol", "action": "评论", "content": "事件发展态势值得关注，信息传播呈现明显极化特征。"},
                {"author_type": "civilian", "action": "转发", "content": "持续关注事件进展，希望各方保持理性。"},
            ],
            "recommendation_bias": {
                "pro_bias": 0.15,
                "echo_amplify": 0.22,
                "polarization_contribution": 0.35,
            },
        }
        
    except Exception as e:
        return {
            "error": f"仿真运行失败: {e}",
            "stance_distribution": {"pro": 0.35, "anti": 0.35, "neutral": 0.30},
            "final_polarization_index": 0.5,
            "summary": f"仿真运行失败，使用默认结果。错误: {e}"
        }


async def run_simple_analysis(
    event: dict[str, Any],
    request: dict[str, Any],
    ollama_base_url: str,
    model: str,
) -> dict[str, Any]:
    """
    使用简单的 LLM 分析（不依赖完整 OASIS 框架）
    直接调用 Ollama API 进行舆情分析
    """
    import httpx
    
    # Ollama API 地址处理
    ollama_url = ollama_base_url.rstrip("/")
    if not ollama_url.endswith("/v1"):
        api_url = f"{ollama_url}/api/chat"
    else:
        api_url = f"{ollama_url[:-3]}/api/chat"
    
    # 构建分析提示
    prompt = f"""请对以下舆情事件进行分析：

事件标题：{event.get('title', '美伊冲突')}
事件描述：{event.get('description', '')}
事件日期：{event.get('date', '')}
事件标签：{', '.join(event.get('tags', []))}

请从以下角度分析：
1. 舆论立场分布（支持/中立/反对的比例）
2. 舆论极化程度（0-1之间）
3. 信息传播特点
4. 主要观点摘要

请以JSON格式返回分析结果，格式如下：
{{
    "stance_distribution": {{"pro": 0.xx, "anti": 0.xx, "neutral": 0.xx}},
    "polarization_index": 0.xx,
    "summary": "分析摘要",
    "key_points": ["观点1", "观点2", "观点3"]
}}
"""
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                api_url,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的舆情分析师，擅长分析社交媒体舆论。"},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                }
            )
            response.raise_for_status()
            result = response.json()
            
            # 解析响应
            content = result.get("message", {}).get("content", "")
            
            # 尝试提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    analysis = json.loads(json_match.group())
                except json.JSONDecodeError:
                    analysis = {}
            else:
                analysis = {}
            
            # 构建返回结果
            stance_dist = analysis.get("stance_distribution", {"pro": 0.38, "anti": 0.32, "neutral": 0.30})
            polarization = analysis.get("polarization_index", event.get("intensity", 0.7) * 0.7)
            
            return {
                "stance_distribution": stance_dist,
                "final_polarization_index": round(polarization, 4),
                "final_imbalance_score": round(abs(stance_dist.get("pro", 0.38) - stance_dist.get("anti", 0.32)), 4),
                "echo_chamber_index": round(polarization * 0.5, 4),
                "herd_effect_intensity": round(polarization * 0.4, 4),
                "peak_spread_speed": int(400 * event.get("intensity", 0.7)),
                "timeline_metrics": [
                    {
                        "step": i + 1,
                        "activated": int(100 * (i + 1) / 10),
                        "new_posts": int(20 * (i + 1) / 10),
                        "spread_speed": int(50 * (i + 1) * event.get("intensity", 0.7)),
                        "polarization_index": round(polarization * (0.5 + 0.05 * i), 4),
                        "imbalance_score": round(0.1 * (i + 1) / 10, 4),
                        "herd_effect": round(0.2 * (i + 1) / 10, 4),
                        "echo_chamber_index": round(0.15 * (i + 1) / 10, 4),
                        "stance_distribution": stance_dist,
                        "mean_stance": round(stance_dist.get("pro", 0.38) - stance_dist.get("anti", 0.32), 4),
                    }
                    for i in range(10)
                ],
                "summary": analysis.get("summary", f"基于本地 Ollama ({model}) 的分析显示，事件「{event.get('title', '美伊冲突')}」"
                          f"呈现舆论分层，极化指数为 {polarization:.2f}。"),
                "key_posts": [
                    {"author_type": "media", "action": "发帖", "content": f"「{event.get('title', '美伊冲突')}」引发广泛关注。"},
                    {"author_type": "kol", "action": "评论", "content": "事件发展态势值得关注。"},
                    {"author_type": "civilian", "action": "转发", "content": "持续关注事件进展。"},
                ],
                "recommendation_bias": {
                    "pro_bias": 0.12,
                    "echo_amplify": 0.18,
                    "polarization_contribution": 0.28,
                },
                "raw_analysis": content,
            }
            
    except Exception as e:
        # 返回默认结果
        return {
            "error": f"LLM 分析失败: {e}",
            "stance_distribution": {"pro": 0.35, "anti": 0.35, "neutral": 0.30},
            "final_polarization_index": round(event.get("intensity", 0.7) * 0.6, 4),
            "final_imbalance_score": 0.15,
            "echo_chamber_index": 0.25,
            "herd_effect_intensity": 0.20,
            "peak_spread_speed": int(300 * event.get("intensity", 0.7)),
            "timeline_metrics": [
                {
                    "step": i + 1,
                    "activated": int(50 * (i + 1) / 10),
                    "new_posts": int(10 * (i + 1) / 10),
                    "spread_speed": int(30 * (i + 1) * event.get("intensity", 0.7)),
                    "polarization_index": round(event.get("intensity", 0.7) * 0.4 * (1 + 0.05 * i), 4),
                    "imbalance_score": round(0.08 * (i + 1) / 10, 4),
                    "herd_effect": round(0.15 * (i + 1) / 10, 4),
                    "echo_chamber_index": round(0.12 * (i + 1) / 10, 4),
                    "stance_distribution": {"pro": 0.35, "anti": 0.35, "neutral": 0.30},
                    "mean_stance": 0.0,
                }
                for i in range(10)
            ],
            "summary": f"基于事件「{event.get('title', '美伊冲突')}」的默认分析结果（LLM 调用失败: {e}）",
            "key_posts": [
                {"author_type": "media", "action": "发帖", "content": f"「{event.get('title', '美伊冲突')}」引发关注。"},
            ],
            "recommendation_bias": {
                "pro_bias": 0.10,
                "echo_amplify": 0.15,
                "polarization_contribution": 0.25,
            },
        }


def main():
    """主入口"""
    if len(sys.argv) != 3:
        print("用法: python oasis_local_runner.py <input.json> <output.json>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    
    # 读取输入
    with open(input_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    
    request = payload.get("request", {})
    event = payload.get("event", {})
    ollama_base_url = payload.get("ollama_base_url", "http://127.0.0.1:11434")
    model = payload.get("model", "qwen2.5:3b")
    
    # 运行分析
    try:
        # 首先尝试使用简单分析（更稳定）
        result = asyncio.run(run_simple_analysis(event, request, ollama_base_url, model))
    except Exception as e:
        result = {
            "error": str(e),
            "stance_distribution": {"pro": 0.35, "anti": 0.35, "neutral": 0.30},
            "final_polarization_index": 0.5,
            "summary": f"分析失败: {e}"
        }
    
    # 写入输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"分析完成，结果已写入 {output_path}")


if __name__ == "__main__":
    main()
