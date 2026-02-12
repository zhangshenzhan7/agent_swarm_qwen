"""Sub Agent implementation."""

import asyncio
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Callable, Awaitable

from .interfaces.sub_agent import ISubAgent
from .interfaces.tool_registry import IToolRegistry
from .interfaces.messaging import IMessageBus
from .models.enums import AgentStatus
from .models.message import MessageType
from .models.task import SubTask
from .models.result import SubTaskResult
from .models.tool import ToolCallRecord
from .models.agent import AgentRole
from .models.context import ExecutionContext
from .qwen.interface import IQwenClient
from .qwen.models import Message, QwenConfig, QwenResponse


class SubAgentError(Exception):
    """子智能体错误"""
    pass


# DashScope 内置工具（服务端执行，通过 API 参数启用，无需客户端处理）
# - web_search: 联网搜索（通过 enable_search=True）
# - web_extractor: 网页抽取（通过 search_options.search_strategy="agent_max"）
# - code_interpreter: 代码解释器（通过 enable_code_interpreter=True）
DASHSCOPE_BUILTIN_TOOLS = {"web_search", "web_extractor", "code_interpreter"}

# 非 Qwen 原生模型使用沙箱代码解释器替代 DashScope 内置 code_interpreter
SANDBOX_CODE_INTERPRETER_TOOL = "sandbox_code_interpreter"

# 非 Qwen 原生模型使用沙箱浏览器替代 DashScope 内置 web_search / web_extractor
SANDBOX_BROWSER_TOOL = "sandbox_browser"


class SubAgentExecutionError(SubAgentError):
    """子智能体执行错误"""
    pass


class InvalidStateTransitionError(SubAgentError):
    """无效状态转换错误"""
    pass


# 定义有效的状态转换
VALID_STATE_TRANSITIONS: Dict[AgentStatus, List[AgentStatus]] = {
    AgentStatus.IDLE: [AgentStatus.RUNNING, AgentStatus.TERMINATED],
    AgentStatus.RUNNING: [AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.TERMINATED],
    AgentStatus.COMPLETED: [],  # 终态，不能转换
    AgentStatus.FAILED: [],  # 终态，不能转换
    AgentStatus.TERMINATED: [],  # 终态，不能转换
}


# 状态变更回调类型
StateChangeCallback = Callable[[str, AgentStatus, AgentStatus], Awaitable[None]]


class SubAgentImpl(ISubAgent):
    """子智能体实现"""
    
    # 最大执行循环次数，防止无限循环
    MAX_ITERATIONS = 20
    
    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        qwen_client: IQwenClient,
        tool_registry: IToolRegistry,
        config: Optional[QwenConfig] = None,
        on_state_change: Optional[StateChangeCallback] = None,
        message_bus: Optional[IMessageBus] = None,
    ):
        """
        初始化子智能体
        
        Args:
            agent_id: 智能体ID
            role: 智能体角色
            qwen_client: Qwen 模型客户端
            tool_registry: 工具注册表
            config: 模型配置（可选，覆盖角色默认配置）
            on_state_change: 状态变更回调函数
            message_bus: 消息总线（可选，用于接收其他智能体的消息）
        """
        self._id = agent_id
        self._role = role
        self._qwen_client = qwen_client
        self._tool_registry = tool_registry
        self._config = config
        self._message_bus = message_bus
        self._status = AgentStatus.IDLE
        self._stop_requested = False
        self._tool_calls: List[ToolCallRecord] = []
        self._token_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self._current_task: Optional[SubTask] = None
        self._on_state_change = on_state_change
        self._created_at = time.time()
        self._completed_at: Optional[float] = None
        self._last_result: Optional[SubTaskResult] = None
        self._execution_history: List[Dict[str, Any]] = []
    
    @property
    def id(self) -> str:
        """获取智能体ID"""
        return self._id
    
    @property
    def role(self) -> AgentRole:
        """获取智能体角色"""
        return self._role
    
    @property
    def created_at(self) -> float:
        """获取创建时间"""
        return self._created_at
    
    @property
    def completed_at(self) -> Optional[float]:
        """获取完成时间"""
        return self._completed_at
    
    @property
    def current_task(self) -> Optional[SubTask]:
        """获取当前执行的任务"""
        return self._current_task
    
    @property
    def last_result(self) -> Optional[SubTaskResult]:
        """获取最后一次执行结果"""
        return self._last_result
    
    @property
    def tool_calls(self) -> List[ToolCallRecord]:
        """获取工具调用记录"""
        return list(self._tool_calls)
    
    @property
    def token_usage(self) -> Dict[str, int]:
        """获取 token 使用统计"""
        return dict(self._token_usage)
    
    @property
    def execution_history(self) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return list(self._execution_history)
    
    def get_status(self) -> AgentStatus:
        """获取当前状态"""
        return self._status
    
    def is_terminal_state(self) -> bool:
        """检查是否处于终态"""
        return self._status in (
            AgentStatus.COMPLETED, 
            AgentStatus.FAILED, 
            AgentStatus.TERMINATED
        )
    
    def can_transition_to(self, new_status: AgentStatus) -> bool:
        """检查是否可以转换到指定状态"""
        valid_transitions = VALID_STATE_TRANSITIONS.get(self._status, [])
        return new_status in valid_transitions
    
    async def _set_status(self, new_status: AgentStatus) -> None:
        """
        设置状态（带验证和回调）
        
        Args:
            new_status: 新状态
            
        Raises:
            InvalidStateTransitionError: 如果状态转换无效
        """
        old_status = self._status
        
        # 如果状态相同，不做任何操作
        if old_status == new_status:
            return
        
        # 验证状态转换
        if not self.can_transition_to(new_status):
            raise InvalidStateTransitionError(
                f"Cannot transition from {old_status.value} to {new_status.value}"
            )
        
        # 更新状态
        self._status = new_status
        
        # 记录状态变更到执行历史
        self._execution_history.append({
            "type": "state_change",
            "timestamp": time.time(),
            "from_status": old_status.value,
            "to_status": new_status.value,
        })
        
        # 如果是终态，记录完成时间
        if self.is_terminal_state():
            self._completed_at = time.time()
        
        # 调用状态变更回调
        if self._on_state_change:
            try:
                await self._on_state_change(self._id, old_status, new_status)
            except Exception:
                # 忽略回调错误，不影响主流程
                pass

    async def stop(self) -> None:
        """
        停止执行
        
        请求停止当前执行，等待执行循环检测到停止请求并优雅退出。
        如果智能体不在运行状态，直接设置为终止状态。
        """
        self._stop_requested = True
        
        # 记录停止请求
        self._execution_history.append({
            "type": "stop_requested",
            "timestamp": time.time(),
        })
        
        # 如果当前正在运行，等待执行完成
        max_wait = 30  # 最多等待30秒
        wait_interval = 0.1
        waited = 0
        
        while self._status == AgentStatus.RUNNING and waited < max_wait:
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        # 如果还在运行状态（超时），强制设置为终止
        if self._status == AgentStatus.RUNNING:
            self._status = AgentStatus.TERMINATED
            self._completed_at = time.time()
            self._execution_history.append({
                "type": "force_terminated",
                "timestamp": time.time(),
                "reason": "stop timeout",
            })
        elif not self.is_terminal_state():
            # 如果不在终态，设置为终止
            await self._set_status(AgentStatus.TERMINATED)
    
    async def cleanup(self) -> None:
        """
        清理智能体资源
        
        释放所有持有的资源，清理临时数据。
        应在智能体不再需要时调用。
        """
        # 确保已停止
        if self._status == AgentStatus.RUNNING:
            await self.stop()
        
        # 清理工具调用记录（保留在执行历史中）
        self._tool_calls.clear()
        
        # 清理当前任务引用
        self._current_task = None
        
        # 记录清理操作
        self._execution_history.append({
            "type": "cleanup",
            "timestamp": time.time(),
        })
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """
        获取执行摘要
        
        Returns:
            包含执行统计信息的字典
        """
        return {
            "agent_id": self._id,
            "role": self._role.name,
            "status": self._status.value,
            "created_at": self._created_at,
            "completed_at": self._completed_at,
            "total_tool_calls": len(self._tool_calls),
            "token_usage": dict(self._token_usage),
            "last_result_success": self._last_result.success if self._last_result else None,
            "execution_history_count": len(self._execution_history),
        }
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        # 沙箱代码解释器是 code_interpreter 的替代品，允许调用
        effective_tools = set(self._role.available_tools)
        if self._uses_sandbox_code_interpreter():
            effective_tools.add(SANDBOX_CODE_INTERPRETER_TOOL)
        # 沙箱浏览器是 web_search/web_extractor 的替代品，允许调用
        if self._uses_sandbox_browser():
            effective_tools.add(SANDBOX_BROWSER_TOOL)
        
        # 检查工具是否在角色允许的工具列表中
        if tool_name not in effective_tools:
            raise SubAgentError(
                f"Tool '{tool_name}' is not available for role '{self._role.name}'. "
                f"Available tools: {list(effective_tools)}"
            )
        
        # 检查工具是否已注册
        tool = self._tool_registry.get_tool(tool_name)
        if not tool:
            raise SubAgentError(
                f"Tool '{tool_name}' is not registered in the system. "
                f"Please use your knowledge to answer instead."
            )
        
        # 调用工具
        record = await self._tool_registry.invoke_tool(
            tool_name=tool_name,
            arguments=arguments,
            agent_id=self._id,
        )
        
        # 记录工具调用
        self._tool_calls.append(record)
        
        if not record.success:
            raise SubAgentError(f"Tool call failed: {record.error}")
        
        return record.result
    
    def _uses_sandbox_code_interpreter(self) -> bool:
        """判断当前角色是否需要使用沙箱代码解释器替代 DashScope 内置 code_interpreter
        
        当角色配置了 code_interpreter 但使用的是非 Qwen 原生模型时，
        DashScope 内置的 code_interpreter 不可用，需要回退到阿里云
        AgentRun Sandbox 提供的 function-calling 工具。
        """
        base = self._config or QwenConfig()
        has_code_interpreter = "code_interpreter" in self._role.available_tools
        is_native = base.model.is_qwen_native()
        return has_code_interpreter and not is_native

    def _uses_sandbox_browser(self) -> bool:
        """判断当前角色是否需要使用沙箱浏览器替代 DashScope 内置 web_search/web_extractor
        
        当角色配置了 web_search 或 web_extractor 但使用的是非 Qwen 原生模型时，
        DashScope 内置的 enable_search 不可用，需要回退到阿里云
        AgentRun BrowserTool 提供的 function-calling 工具。
        """
        base = self._config or QwenConfig()
        has_web = "web_search" in self._role.available_tools or "web_extractor" in self._role.available_tools
        is_native = base.model.is_qwen_native()
        return has_web and not is_native

    def _get_effective_builtin_tools(self) -> set:
        """获取当前模型实际可用的 DashScope 内置工具集合
        
        非 Qwen 原生模型不支持任何 DashScope 内置工具。
        """
        base = self._config or QwenConfig()
        if not base.model.is_qwen_native():
            return set()  # 第三方模型无 DashScope 内置工具
        return DASHSCOPE_BUILTIN_TOOLS

    def _build_system_prompt(self, subtask: SubTask) -> str:
        """构建系统提示 - 精简版，减少 token 消耗同时保留核心指令"""
        import datetime
        
        now = datetime.datetime.now()
        current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
        current_year = now.year
        current_month = now.month
        current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        
        # 精简时间声明
        time_info = f"[系统时间] {current_datetime} {current_weekday} | 以{current_year}年{current_month}月为基准，不要使用训练数据中的旧时间。"
        
        # 收集 DashScope 内置能力描述
        builtin_capabilities = []
        effective_builtins = self._get_effective_builtin_tools()
        if "web_search" in self._role.available_tools and "web_search" in effective_builtins:
            builtin_capabilities.append("- 联网搜索：可实时搜索互联网获取最新信息")
        if "web_extractor" in self._role.available_tools and "web_extractor" in effective_builtins:
            builtin_capabilities.append("- 网页抽取：可抓取和解析指定网页的完整内容")
        if "code_interpreter" in self._role.available_tools and "code_interpreter" in effective_builtins:
            builtin_capabilities.append("- 代码解释器：可编写并执行 Python 代码进行计算和数据分析")
        
        # 获取实际可用的 function calling 工具
        available_tools = []
        tool_descriptions = []
        for tool_name in self._role.available_tools:
            if tool_name in effective_builtins:
                continue
            # 非 Qwen 模型：code_interpreter 被替换为 sandbox_code_interpreter
            if tool_name == "code_interpreter" and self._uses_sandbox_code_interpreter():
                tool = self._tool_registry.get_tool(SANDBOX_CODE_INTERPRETER_TOOL)
                if tool:
                    available_tools.append(SANDBOX_CODE_INTERPRETER_TOOL)
                    tool_descriptions.append(f"  - {SANDBOX_CODE_INTERPRETER_TOOL}: {tool.description}")
                continue
            # 非 Qwen 模型：web_search/web_extractor 被替换为 sandbox_browser
            if tool_name in ("web_search", "web_extractor") and self._uses_sandbox_browser():
                # 只添加一次 sandbox_browser（web_search 和 web_extractor 共用）
                if SANDBOX_BROWSER_TOOL not in available_tools:
                    tool = self._tool_registry.get_tool(SANDBOX_BROWSER_TOOL)
                    if tool:
                        available_tools.append(SANDBOX_BROWSER_TOOL)
                        tool_descriptions.append(f"  - {SANDBOX_BROWSER_TOOL}: {tool.description}")
                continue
            tool = self._tool_registry.get_tool(tool_name)
            if tool:
                available_tools.append(tool_name)
                tool_descriptions.append(f"  - {tool_name}: {tool.description}")
        
        tools_parts = []
        if builtin_capabilities:
            tools_parts.append("## 内置能力（自动启用）\n" + "\n".join(builtin_capabilities))
        if available_tools:
            tools_list = "\n".join(tool_descriptions)
            tools_parts.append(f"## 可调用工具\n{tools_list}")
        
        if tools_parts:
            tools_instruction = "\n\n".join(tools_parts) + "\n\n使用策略：分析任务需求 → 选择合适工具 → 执行调用 → 验证结果。搜索不理想时调整关键词，遇到错误时尝试其他方法。"
        else:
            tools_instruction = "当前无外部工具，直接运用知识和推理完成任务。"
        
        return f"""{time_info}

{self._role.system_prompt}

# 当前任务
{subtask.content}

# 主题约束（最高优先级）
你必须严格围绕上述任务主题产出内容。具体要求：
- 搜索时只使用与任务直接相关的关键词，忽略所有无关搜索结果
- 如果搜索结果中混入了其他领域的内容（如任务是前端框架但结果涉及AI/深度学习），必须丢弃这些无关信息
- 输出中禁止包含与任务主题无关的数据、案例或分析
- 只讨论任务明确要求的对象，禁止引入任务未提及的对象（如任务要求分析A/B/C，禁止额外讨论D/E）
- 所有数据必须标注来源（如"据 State of JS 2025 调查"），同一指标只使用一个权威来源，避免口径冲突
- 遇到搜索信息不足时，使用已有专业知识补充，而非填充无关内容

# 数据质量规则
- 搜索类任务：必须报告搜索结果中发现的精确版本号（如 React 18.3.1），不要凭印象编造版本号
- 综合/写作类任务：如果基于前序任务结果撰写，必须保留前序结果中的原始数据来源标注（如"State of JS 2024""npm trends"），禁止用"综合前序任务报告"等模糊来源替代
- 当搜索结果中的数值与常识明显不符时（如某框架体积数倍于预期），必须标注"该数据待验证"
- 涉及软件版本时，优先报告搜索到的确切版本号和发布日期，而非推测未来版本

# 时间锚点规则（重要）
- 如果任务描述中明确指定了分析年份（如"2025年"），你的所有分析、数据、报告标题和结论必须以该年份为基准
- 禁止使用系统当前时间（{current_year}年）替代任务指定年份。例如：任务要求"2025年"分析时，报告标题应写"2025年"而非"{current_year}年"
- 搜索时优先查找任务指定年份的数据；如果该年份数据不足，可使用最近年份数据并注明"截至XXXX年的最新数据"
- 对尚未发生的事件，明确标注"预计"或"规划中"，区分事实与预测

{tools_instruction}

# 输出要求
1. 直接输出最终结果，使用 Markdown 格式
2. 搜索/数据收集类任务：不少于500字；综合分析/报告撰写类任务：不少于2000字
3. 提供具体数据、案例支撑，体现专业深度
4. 禁止输出思考过程、"我认为"/"让我分析"等过程性语句
5. 对不确定的信息标注置信度
6. 引用数据时必须注明出处和统计年份（如"据 State of JS 2024 调查，React 使用率为 63%"）"""
    
    def _build_tools_schema(self) -> List[Dict[str, Any]]:
        """构建工具 schema 列表（只包含实际注册的 function calling 工具）
        
        DashScope 内置工具（web_search, web_extractor, code_interpreter）通过
        API 参数启用，不在 tools schema 中列出。
        
        对于非 Qwen 原生模型：
        - code_interpreter 会被替换为 sandbox_code_interpreter
        - web_search/web_extractor 会被替换为 sandbox_browser
        并作为 function calling 工具列出。
        """
        effective_builtins = self._get_effective_builtin_tools()
        tools_schema = []
        sandbox_browser_added = False
        for tool_name in self._role.available_tools:
            # 跳过当前模型实际可用的 DashScope 内置工具
            if tool_name in effective_builtins:
                continue
            # 非 Qwen 模型：code_interpreter → sandbox_code_interpreter
            if tool_name == "code_interpreter" and self._uses_sandbox_code_interpreter():
                tool = self._tool_registry.get_tool(SANDBOX_CODE_INTERPRETER_TOOL)
                if tool:
                    tools_schema.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters_schema,
                        }
                    })
                continue
            # 非 Qwen 模型：web_search/web_extractor → sandbox_browser（只添加一次）
            if tool_name in ("web_search", "web_extractor") and self._uses_sandbox_browser():
                if not sandbox_browser_added:
                    tool = self._tool_registry.get_tool(SANDBOX_BROWSER_TOOL)
                    if tool:
                        tools_schema.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.parameters_schema,
                            }
                        })
                        sandbox_browser_added = True
                continue
            tool = self._tool_registry.get_tool(tool_name)
            if tool:
                tools_schema.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema,
                    }
                })
        return tools_schema
    
    def _build_request_config(self) -> QwenConfig:
        """根据角色的 available_tools 构建单次请求的 QwenConfig
        
        不同角色绑定不同的 DashScope 内置工具：
        - web_search + web_extractor → enable_search + search_strategy=agent_max + enable_thinking
        - code_interpreter → enable_code_interpreter + enable_thinking
        
        注意：
        - agent_max 策略和 code_interpreter 均要求 enable_thinking=True，
          即使角色原始配置中 enable_thinking=False，也会被自动覆盖。
        - 第三方模型（DeepSeek/GLM/Kimi）不支持 enable_search / enable_code_interpreter，
          这些功能会被自动禁用。此时 code_interpreter 会回退到
          sandbox_code_interpreter（阿里云 AgentRun Sandbox），通过 function calling 调用。
        """
        base = self._config or QwenConfig()
        is_native = base.model.is_qwen_native()
        
        has_search = "web_search" in self._role.available_tools
        has_extractor = "web_extractor" in self._role.available_tools
        has_code_interpreter = "code_interpreter" in self._role.available_tools
        
        # 第三方模型不支持 Qwen 专属的联网搜索和代码解释器
        if not is_native:
            has_search = False
            has_extractor = False
            has_code_interpreter = False
        
        # agent_max 已禁用，code_interpreter 需要 enable_thinking=True
        needs_thinking = has_code_interpreter
        # searcher/fact_checker 无需深度思考，加速响应
        is_data_role = self._role.name in ("searcher", "fact_checker")
        enable_thinking = True if needs_thinking else (False if is_data_role else base.enable_thinking)
        
        # 不支持 thinking 的模型强制关闭
        if enable_thinking and not base.model.supports_thinking():
            enable_thinking = False
        
        return QwenConfig(
            model=base.model,
            api_key=base.api_key,
            base_url=base.base_url,
            temperature=base.temperature,
            max_tokens=base.max_tokens,
            timeout=base.timeout,
            retry_attempts=base.retry_attempts,
            top_p=base.top_p,
            # 联网搜索：角色有 web_search 或 web_extractor 时启用（仅 Qwen 原生模型）
            enable_search=has_search or has_extractor,
            # 网页抽取：不使用 agent_max（与 thinking 模式不兼容）
            search_strategy=None,
            # 深度思考：agent_max / code_interpreter 强制开启
            enable_thinking=enable_thinking,
            # 代码解释器：角色有 code_interpreter 时启用（仅 Qwen 原生模型）
            enable_code_interpreter=has_code_interpreter,
        )

    async def _process_tool_calls(
        self, 
        tool_calls: List[Dict[str, Any]],
        messages: List[Message],
    ) -> List[Message]:
        """
        处理工具调用
        
        Args:
            tool_calls: 工具调用列表
            messages: 当前消息历史
            
        Returns:
            更新后的消息历史
        """
        # 添加助手消息（包含工具调用）
        assistant_msg = Message(
            role="assistant",
            content="",
            tool_calls=tool_calls,
        )
        messages.append(assistant_msg)
        
        # 处理每个工具调用
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id", str(uuid.uuid4()))
            function_info = tool_call.get("function", {})
            tool_name = function_info.get("name", "")
            arguments_str = function_info.get("arguments", "{}")
            
            try:
                # 解析参数
                if isinstance(arguments_str, str):
                    arguments = json.loads(arguments_str)
                else:
                    arguments = arguments_str
                
                # 调用工具
                result = await self.call_tool(tool_name, arguments)
                result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                
            except Exception as e:
                result_str = f"Error: {str(e)}"
            
            # 添加工具结果消息
            tool_msg = Message(
                role="tool",
                content=result_str,
                tool_call_id=tool_call_id,
            )
            messages.append(tool_msg)
        
        return messages
    @staticmethod
    def _parse_text_tool_calls(content: str) -> Optional[List[Dict[str, Any]]]:
        """
        从模型文本输出中解析工具调用（deepseek-r1 等模型的兼容处理）。

        某些第三方模型（如 deepseek-r1）不通过 API 结构化字段返回 tool_calls，
        而是在 content 中以特殊标记输出工具调用。本方法识别以下格式：

        格式 1 — DeepSeek 原生标记:
            function<｜tool▁sep｜>tool_name
            ```json
            {"arg": "value"}
            ```<｜tool▁call▁end｜>

        格式 2 — JSON 数组:
            ```json
            [{"name": "tool_name", "arguments": {"arg": "value"}}]
            ```

        Returns:
            解析出的 tool_calls 列表（与 DashScope API 格式一致），或 None
        """
        import re

        if not content:
            return None

        tool_calls = []

        # 格式 1: DeepSeek 原生标记
        # function<｜tool▁sep｜>sandbox_browser\n```json\n{...}\n```<｜tool▁call▁end｜>
        ds_pattern = re.compile(
            r'function\s*[<＜][\s\S]*?tool[\s\u2581_]sep[\s\S]*?[>＞]\s*'
            r'(\w+)\s*'
            r'(?:```(?:json)?\s*)?'
            r'(\{[\s\S]*?\})'
            r'(?:\s*```)?',
            re.MULTILINE,
        )
        for m in ds_pattern.finditer(content):
            tool_name = m.group(1).strip()
            args_str = m.group(2).strip()
            try:
                json.loads(args_str)  # validate
            except json.JSONDecodeError:
                continue
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": args_str,
                },
            })

        if tool_calls:
            return tool_calls

        # 格式 2: JSON 数组 — [{"name": "...", "arguments": {...}}]
        json_array_pattern = re.compile(
            r'```(?:json)?\s*(\[[\s\S]*?\])\s*```',
            re.MULTILINE,
        )
        for m in json_array_pattern.finditer(content):
            try:
                arr = json.loads(m.group(1))
                if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "name" in arr[0]:
                    for item in arr:
                        name = item.get("name", "")
                        args = item.get("arguments", {})
                        if name:
                            tool_calls.append({
                                "id": f"call_{uuid.uuid4().hex[:8]}",
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
                                },
                            })
            except (json.JSONDecodeError, TypeError):
                continue

        return tool_calls if tool_calls else None

    
    def _update_token_usage(self, usage: Dict[str, int]) -> None:
        """更新 token 使用统计"""
        self._token_usage["prompt_tokens"] += usage.get("input_tokens", 0)
        self._token_usage["completion_tokens"] += usage.get("output_tokens", 0)
        self._token_usage["total_tokens"] += usage.get("total_tokens", 0)

    async def execute(self, subtask: SubTask, context: ExecutionContext) -> SubTaskResult:
        """
        执行子任务 - 优化版，增强自主解决问题能力
        
        实现执行循环：
        1. 发送任务给模型
        2. 如果模型返回工具调用，执行工具并将结果返回给模型
        3. 重复步骤2直到模型返回最终答案或达到最大迭代次数
        4. 如果遇到错误，尝试自动恢复
        
        Args:
            subtask: 要执行的子任务
            context: 执行上下文
            
        Returns:
            子任务执行结果
        """
        self._current_task = subtask
        self._stop_requested = False
        self._tool_calls = []
        self._token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        
        # 记录执行开始
        start_time = time.time()
        self._execution_history.append({
            "type": "execution_start",
            "timestamp": start_time,
            "subtask_id": subtask.id,
        })
        
        print(f"[SubAgent {self._id[:8]}] 开始执行: {subtask.content[:50]}...")
        
        # 设置运行状态
        await self._set_status(AgentStatus.RUNNING)
        
        output = None
        error = None
        success = False
        retry_count = 0
        max_retries = 2  # 最大重试次数
        
        while retry_count <= max_retries:
            try:
                # 构建初始消息
                system_prompt = self._build_system_prompt(subtask)
                messages: List[Message] = [
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=f"请开始执行任务：{subtask.content}"),
                ]
                
                # 如果是重试，添加重试提示
                if retry_count > 0:
                    messages.append(Message(
                        role="user", 
                        content=f"[重试 {retry_count}/{max_retries}] 上次执行遇到问题：{error}。请尝试其他方法完成任务。"
                    ))
                
                # 构建工具 schema
                tools_schema = self._build_tools_schema()
                # 根据角色绑定的内置工具构建请求配置
                request_config = self._build_request_config()
                sandbox_ci = self._uses_sandbox_code_interpreter()
                print(f"[SubAgent {self._id[:8]}] 可用工具数: {len(tools_schema)}, "
                      f"联网搜索: {request_config.enable_search}, "
                      f"代码解释器: {request_config.enable_code_interpreter}"
                      f"{' (沙箱回退)' if sandbox_ci else ''}, "
                      f"重试次数: {retry_count}")
                
                # 执行循环
                iteration = 0
                consecutive_errors = 0  # 连续错误计数
                max_consecutive_errors = 3  # 最大连续错误次数
                
                while iteration < self.MAX_ITERATIONS:
                    # 检查是否请求停止
                    if self._stop_requested:
                        error = "Execution stopped by request"
                        self._execution_history.append({
                            "type": "execution_stopped",
                            "timestamp": time.time(),
                            "iteration": iteration,
                        })
                        break
                    
                    # Check for incoming messages from the message bus
                    if self._message_bus:
                        try:
                            incoming_messages = await self._message_bus.receive_messages(self._id)
                            for msg in incoming_messages:
                                if msg.msg_type == MessageType.SHUTDOWN:
                                    self._stop_requested = True
                                    break
                                # Inject non-shutdown messages as context
                                context_msg = Message(
                                    role="system",
                                    content=f"[Message from {msg.sender_id}]: {msg.content}"
                                )
                                messages.append(context_msg)
                            # If shutdown was requested via message, break the loop
                            if self._stop_requested:
                                error = "Execution stopped by SHUTDOWN message"
                                self._execution_history.append({
                                    "type": "execution_stopped",
                                    "timestamp": time.time(),
                                    "iteration": iteration,
                                    "reason": "shutdown_message",
                                })
                                break
                        except Exception as msg_err:
                            # Message bus errors should not crash execution
                            print(f"[SubAgent {self._id[:8]}] Message bus error: {msg_err}")
                            self._execution_history.append({
                                "type": "message_bus_error",
                                "timestamp": time.time(),
                                "error": str(msg_err),
                            })
                    
                    iteration += 1
                    print(f"[SubAgent {self._id[:8]}] 迭代 {iteration}/{self.MAX_ITERATIONS}")
                    
                    # 调用模型（使用按角色构建的请求配置）
                    response: QwenResponse = await self._qwen_client.chat(
                        messages=messages,
                        tools=tools_schema if tools_schema else None,
                        config=request_config,
                    )
                    
                    # 更新 token 使用
                    self._update_token_usage(response.usage)
                    
                    # 检查是否有工具调用
                    effective_tool_calls = response.tool_calls

                    # 兼容处理：某些第三方模型（如 deepseek-r1）将工具调用
                    # 以文本形式输出在 content 中，而非结构化 tool_calls 字段
                    if not effective_tool_calls and tools_schema and response.content:
                        parsed = self._parse_text_tool_calls(response.content)
                        if parsed:
                            effective_tool_calls = parsed
                            print(f"[SubAgent {self._id[:8]}] 从文本输出中解析到工具调用")

                    if effective_tool_calls:
                        tool_names = [tc.get('function',{}).get('name','?') for tc in effective_tool_calls]
                        print(f"[SubAgent {self._id[:8]}] 模型请求调用工具: {tool_names}")
                        
                        # 处理工具调用
                        try:
                            messages = await self._process_tool_calls(
                                effective_tool_calls, 
                                messages,
                            )
                            # 检查工具结果中是否有错误（_process_tool_calls 内部捕获异常）
                            tool_error_count = sum(
                                1 for m in messages[-len(effective_tool_calls):]
                                if m.role == "tool" and m.content and m.content.startswith("Error:")
                            )
                            if tool_error_count > 0:
                                consecutive_errors += tool_error_count
                                print(f"[SubAgent {self._id[:8]}] 工具返回错误 ({consecutive_errors}/{max_consecutive_errors})")
                            else:
                                consecutive_errors = 0  # 重置连续错误计数
                        except Exception as tool_error:
                            consecutive_errors += 1
                            print(f"[SubAgent {self._id[:8]}] 工具调用错误 ({consecutive_errors}/{max_consecutive_errors}): {tool_error}")
                            
                            # 添加错误信息到消息中，让模型知道并尝试其他方法
                            messages.append(Message(
                                role="assistant",
                                content=f"工具调用失败: {tool_error}"
                            ))
                            messages.append(Message(
                                role="user",
                                content="工具调用遇到问题，请尝试其他方法或直接根据已有信息回答。"
                            ))
                            
                            if consecutive_errors >= max_consecutive_errors:
                                print(f"[SubAgent {self._id[:8]}] 连续错误过多，尝试直接回答")
                                # 让模型尝试不使用工具直接回答
                                tools_schema = []
                    else:
                        # 没有工具调用，任务完成
                        output = response.content
                        success = True
                        print(f"[SubAgent {self._id[:8]}] 任务完成，输出长度: {len(output) if output else 0}")
                        break
                
                # 检查是否达到最大迭代次数
                if iteration >= self.MAX_ITERATIONS and not success:
                    error = f"Max iterations ({self.MAX_ITERATIONS}) reached without completion"
                    print(f"[SubAgent {self._id[:8]}] 达到最大迭代次数")
                
                # 如果成功，跳出重试循环
                if success:
                    break
                    
            except Exception as e:
                import traceback
                error = str(e)
                print(f"[SubAgent {self._id[:8]}] 执行异常: {error}")
                print(traceback.format_exc())
                self._execution_history.append({
                    "type": "execution_error",
                    "timestamp": time.time(),
                    "error": error,
                    "retry_count": retry_count,
                })
            
            # 如果不成功，增加重试计数
            if not success:
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"[SubAgent {self._id[:8]}] 准备重试 ({retry_count}/{max_retries})...")
                    await asyncio.sleep(1)  # 短暂等待后重试
        
        execution_time = time.time() - start_time
        
        # 设置最终状态
        if self._stop_requested:
            await self._set_status(AgentStatus.TERMINATED)
        elif success:
            await self._set_status(AgentStatus.COMPLETED)
        else:
            await self._set_status(AgentStatus.FAILED)
        
        # 记录执行完成
        self._execution_history.append({
            "type": "execution_complete",
            "timestamp": time.time(),
            "success": success,
            "execution_time": execution_time,
            "retry_count": retry_count,
        })
        
        # 创建结果
        result = SubTaskResult(
            subtask_id=subtask.id,
            agent_id=self._id,
            success=success,
            output=output,
            error=error,
            tool_calls=list(self._tool_calls),
            execution_time=execution_time,
            token_usage=self._token_usage,
        )
        
        # 保存最后结果
        self._last_result = result
        self._current_task = None
        
        return result
