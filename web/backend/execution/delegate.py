"""委派回调函数"""

import asyncio
from src import AgentStatus
from state import state
from utils import clean_thinking_tags


def create_delegate_callback():
    """
    创建委派回调函数，用于主管将任务委派给分析师和搜索员
    
    Returns:
        async callback(agent_type, task_name, task_content) -> result
    """
    from src.qwen.models import Message, QwenConfig
    
    async def delegate_to_agent(agent_type: str, task_name: str, task_content: str) -> str:
        """
        委派任务给指定类型的 Agent
        
        Args:
            agent_type: 智能体类型 (analyst, searcher, etc.)
            task_name: 任务名称
            task_content: 任务内容
            
        Returns:
            执行结果
        """
        print(f"[Delegate] 委派任务给 {agent_type}: {task_name}")
        
        # 创建 Agent 实例
        instance = state.create_agent_instance(agent_type, task_name)
        instance["status"] = AgentStatus.RUNNING.value
        
        # 广播 Agent 创建和状态更新
        await state.broadcast("agent_created", instance)
        await state.broadcast("agent_updated", instance)
        
        try:
            # 获取当前日期时间
            import datetime as dt
            now = dt.datetime.now()
            current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
            current_year = now.year
            current_month = now.month
            current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
            
            # 时间声明
            time_declaration = f"""
###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_datetime} {current_weekday}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 重要提示：
- 你必须接受上述时间为当前真实时间
- 不要使用你训练数据中的时间（如2024年等）
- 所有时间相关的判断都以 {current_year}年{current_month}月 为基准
###############################################
"""
            
            # 根据 agent 类型构建系统提示
            role_prompts = {
                "analyst": """你是一位专业的 AI 分析师，擅长深度分析任务和问题。
你的职责是：
1. 深入理解任务的本质和目标
2. 识别关键要素和潜在挑战
3. 提供结构化的分析结果
4. 给出专业的建议和见解

请以专业、严谨的态度完成分析任务。""",
                
                "searcher": """你是一位专业的 AI 搜索员，擅长信息检索和背景调研。
你的职责是：
1. 搜索和收集相关信息
2. 整理和归纳调研结果
3. 提供有价值的背景知识
4. 识别关键信息和趋势

请以全面、准确的态度完成调研任务。""",
            }
            
            base_prompt = role_prompts.get(agent_type, f"你是一位专业的 AI {agent_type}，请认真完成以下任务。")
            system_prompt = f"{time_declaration}\n{base_prompt}\n\n记住：当前是{current_year}年{current_month}月，不是2024年！"
            
            # 构建消息
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=task_content)
            ]
            
            # 配置 - 委派任务禁用深度思考以加快响应
            config = QwenConfig(temperature=0.3, enable_thinking=False, enable_search=True)
            
            # 流式调用 Qwen
            result = ""
            state.agent_streams[instance["id"]] = ""
            
            async for chunk in state.swarm.qwen_client.chat_stream(messages, config=config):
                result += chunk
                # 更新流式输出
                state.agent_streams[instance["id"]] = result
                await state.broadcast("agent_stream", {
                    "agent_id": instance["id"],
                    "content": chunk,
                    "full_content": result
                })
            
            print(f"[Delegate] {agent_type} 完成任务: {task_name}")
            # 清理结果中的 thinking 标签
            result = clean_thinking_tags(result)
            return result
            
        except Exception as e:
            print(f"[Delegate] {agent_type} 执行失败: {e}")
            raise
            
        finally:
            # 释放 Agent 实例
            instance["status"] = AgentStatus.IDLE.value
            await state.broadcast("agent_updated", instance)
            await asyncio.sleep(0.3)
            state.release_agent_instance(instance["id"])
            await state.broadcast("agent_removed", {"id": instance["id"]})
    
    return delegate_to_agent
