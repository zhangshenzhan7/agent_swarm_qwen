"""会议室剧情生成路由"""

import json

from fastapi import APIRouter, HTTPException

from state import state

router = APIRouter()


@router.post("/api/meeting/generate-story")
async def generate_meeting_story():
    """使用 AI 生成会议室趣味剧情"""
    if not state.swarm or not state.swarm.qwen_client:
        raise HTTPException(status_code=503, detail="AI 服务未初始化，请先配置 API Key")

    from src.qwen.models import Message, QwenConfig

    prompt = """你是一个办公室情景剧编剧，请为 AI 员工会议室生成有趣的剧情内容。

我们的 AI 办公室有以下角色：
- 👨‍💼 主管 (supervisor) - 男性，负责分配任务
- 👩‍🔬 研究员 (researcher) - 女性，负责调研分析
- 👨‍💻 程序员 (coder) - 男性，负责写代码
- 👩‍💼 分析师 (analyst) - 女性，负责数据分析
- 👩‍🎨 文案 (writer) - 女性，负责撰写文案
- 👨‍🔍 搜索员 (searcher) - 男性，负责信息检索
- 👩‍📝 总结员 (summarizer) - 女性，负责汇总报告

请生成以下内容（JSON格式）：

1. gossips: 3条办公室八卦/趣闻（带emoji和message）
2. activities: 2个集体活动（带emoji、name、message）
3. romances: 2个办公室恋情故事（带role1、role2、story）
4. workPhrases: 每个角色2条工作时的状态语（角色key -> 短语数组）
5. idlePhrases: 每个角色2条休息时的状态语（角色key -> 短语数组）

要求：
- 内容要有趣、轻松、正能量
- 八卦要有办公室特色，可以涉及角色互动
- 恋情故事要含蓄浪漫，不要太直白
- 状态语要简短有趣，带emoji
- 每次生成的内容要有差异性和新鲜感

直接返回JSON，不要其他内容："""

    try:
        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.9, enable_thinking=False)

        result = ""
        async for chunk in state.swarm.qwen_client.chat_stream(messages, config=config):
            result += chunk

        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        story_data = json.loads(result)
        return {"success": True, "data": story_data}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON 解析失败: {str(e)}", "raw": result[:500] if result else ""}
    except Exception as e:
        return {"success": False, "error": str(e)}
