"""AI 评测脚本 - 使用 qwen3-max 对 AgentSwarm 输出进行多维度评测，然后根据结果优化"""

import asyncio
import os
import sys
import time
import json

# os.environ["DASHSCOPE_API_KEY"] = "your-dashscope-api-key"  # Set via environment variable
sys.path.insert(0, os.path.dirname(__file__))

from src import AgentSwarm, AgentSwarmConfig
from src.qwen.dashscope_client import DashScopeClient
from src.qwen.models import QwenConfig, QwenModel, Message


EVAL_PROMPT = """你是一个专业的内容质量评测专家。请对以下 AI 多智能体协作系统的输出进行严格评测。

## 原始任务
{task}

## 系统输出
{output}

## 评测维度（每项 1-10 分，必须给出明确数字分数）

请从以下 6 个维度严格评分，并给出具体理由和改进建议：

### 1. 专业深度 (1-10)
- 是否引用了真实数据源和权威报告？
- 数据是否准确、有具体数值支撑？
- 分析是否有深度，而非泛泛而谈？

### 2. 内容丰富度 (1-10)
- 是否全面覆盖了任务要求的所有维度？
- 信息量是否充足？
- 是否有独到的观察或洞察？

### 3. 结构化程度 (1-10)
- 是否有清晰的层次结构？
- 段落组织是否合理？
- 是否使用了表格、列表等辅助呈现？

### 4. 可操作性 (1-10)
- 建议是否具体、可执行？
- 是否针对不同场景给出差异化建议？
- 是否有明确的决策框架？

### 5. 逻辑连贯性 (1-10)
- 各部分之间是否有逻辑衔接？
- 论证过程是否严谨？
- 结论是否从分析中自然推导？

### 6. 信息时效性 (1-10)
- 数据和信息是否为最新（2025年）？
- 是否反映了最新的技术趋势？
- 版本号和特性是否与最新发布一致？

## 输出格式（严格按此 JSON 格式输出）

```json
{
  "scores": {
    "专业深度": <分数>,
    "内容丰富度": <分数>,
    "结构化程度": <分数>,
    "可操作性": <分数>,
    "逻辑连贯性": <分数>,
    "信息时效性": <分数>
  },
  "overall_score": <加权平均分>,
  "strengths": ["优点1", "优点2", "优点3"],
  "weaknesses": ["不足1", "不足2", "不足3"],
  "improvement_suggestions": [
    "具体优化建议1（指出哪个阶段需要改进，怎么改）",
    "具体优化建议2",
    "具体优化建议3"
  ],
  "summary": "一段话总结评测结论"
}
```
"""


async def run_task_and_evaluate():
    """执行任务并用 qwen3-max 评测"""

    task_content = "对比分析 React、Vue、Angular 三大前端框架在2025年的技术生态、性能表现、学习曲线和企业采用率，给出技术选型建议。"

    # ========== Step 1: 执行任务 ==========
    print("=" * 80)
    print("Step 1: 执行任务")
    print("=" * 80)

    config = AgentSwarmConfig(
        enable_team_mode=True,
        enable_search=True,
        complexity_threshold=3.0,
        execution_timeout=900.0,
        agent_timeout=240.0,
    )
    swarm = AgentSwarm(config=config)

    start = time.time()
    result = await swarm.execute(task_content)
    elapsed = time.time() - start

    output = result.output or ""
    output_str = str(output) if not isinstance(output, str) else output

    print(f"\n执行完成:")
    print(f"  成功: {result.success}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  子结果: {len(result.sub_results)}")
    print(f"  输出长度: {len(output_str)} 字符")

    if not output_str or len(output_str) < 100:
        print("输出过短，跳过评测")
        return None

    # ========== Step 2: AI 评测 ==========
    print("\n" + "=" * 80)
    print("Step 2: qwen3-max 评测")
    print("=" * 80)

    eval_config = QwenConfig(
        model=QwenModel.QWEN3_MAX,
        temperature=0.3,
        enable_thinking=True,
        enable_search=False,
    )
    eval_client = DashScopeClient(eval_config)

    # 截取输出（避免超长）
    eval_output = output_str[:15000] if len(output_str) > 15000 else output_str

    eval_content = EVAL_PROMPT.replace("{task}", task_content).replace("{output}", eval_output)
    eval_messages = [
        Message(role="user", content=eval_content)
    ]

    print("正在评测...")
    eval_response = await eval_client.chat(messages=eval_messages, config=eval_config)
    eval_text = eval_response.content or ""

    # 解析 JSON
    eval_result = None
    try:
        # 尝试从回复中提取 JSON
        json_start = eval_text.find("{")
        json_end = eval_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = eval_text[json_start:json_end]
            eval_result = json.loads(json_str)
    except json.JSONDecodeError:
        pass

    if eval_result:
        print("\n📊 评测结果:")
        scores = eval_result.get("scores", {})
        for dim, score in scores.items():
            bar = "█" * int(score) + "░" * (10 - int(score))
            print(f"  {dim:8s}: {bar} {score}/10")

        overall = eval_result.get("overall_score", 0)
        print(f"\n  综合评分: {overall}/10")

        print("\n✅ 优点:")
        for s in eval_result.get("strengths", []):
            print(f"  + {s}")

        print("\n❌ 不足:")
        for w in eval_result.get("weaknesses", []):
            print(f"  - {w}")

        print("\n💡 优化建议:")
        for i, sug in enumerate(eval_result.get("improvement_suggestions", []), 1):
            print(f"  {i}. {sug}")

        print(f"\n📝 总结: {eval_result.get('summary', '')}")
    else:
        print("\n评测结果解析失败，原始输出:")
        print(eval_text[:3000])

    return {
        "task": task_content,
        "execution_time": elapsed,
        "output_length": len(output_str),
        "sub_results": len(result.sub_results),
        "success": result.success,
        "eval_result": eval_result,
        "raw_eval": eval_text[:3000],
    }


if __name__ == "__main__":
    result = asyncio.run(run_task_and_evaluate())
    if result and result.get("eval_result"):
        # 保存结果
        with open("eval_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n评测结果已保存到 eval_result.json")
