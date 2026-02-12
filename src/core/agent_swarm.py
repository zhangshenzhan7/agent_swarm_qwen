"""AgentSwarm - Unified entry point for the Qwen Agent Swarm system."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable, TYPE_CHECKING

from ..utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from ..core.main_agent import MainAgent

from ..task_decomposer import TaskDecomposer
from ..agent_scheduler import AgentScheduler
from ..result_aggregator import ResultAggregatorImpl
from ..context_manager import ExecutionContextManager
from ..tool_registry import ToolRegistry
from ..long_text_processor import LongTextProcessor, LongTextConfig
from ..qwen.interface import IQwenClient
from ..qwen.dashscope_client import DashScopeClient
from ..qwen.local_client import LocalQwenClient
from ..qwen.models import QwenConfig, QwenModel
from ..models.task import Task
from ..models.result import TaskResult
from ..models.enums import TaskStatus
from ..models.tool import ToolDefinition
from ..supervisor import Supervisor, SupervisorConfig, StreamCallback


@dataclass
class AgentSwarmConfig:
    """AgentSwarm 配置。
    
    Attributes:
        api_key: API 密钥
        model: Qwen 模型
        base_url: 本地模型 URL
        use_local_model: 是否使用本地模型
        enable_search: 是否启用联网搜索
        search_strategy: 搜索策略
        max_concurrent_agents: 最大并发智能体数
        max_tool_calls: 最大工具调用次数
        agent_timeout: 智能体超时时间
        complexity_threshold: 复杂度阈值
        execution_timeout: 执行超时时间
        enable_long_text_processing: 是否启用长文本处理
        enable_team_mode: 是否启用团队模式
    """
    # Qwen 模型配置
    api_key: Optional[str] = None
    model: QwenModel = QwenModel.QWEN3_MAX
    base_url: Optional[str] = None
    use_local_model: bool = False
    enable_search: bool = True
    search_strategy: Optional[str] = None
    
    # 调度器配置
    max_concurrent_agents: int = 100
    max_tool_calls: int = 1500
    agent_timeout: float = 300.0
    
    # 主智能体配置
    complexity_threshold: float = 3.0
    execution_timeout: float = 3600.0
    
    # 长文本处理配置
    enable_long_text_processing: bool = True
    
    # 执行模式配置
    enable_team_mode: bool = False
    
    # 沙箱代码解释器配置（为非 Qwen 模型提供代码执行能力）
    sandbox_account_id: Optional[str] = None  # 阿里云主账号 ID
    sandbox_region_id: str = "cn-hangzhou"
    sandbox_template_name: str = "python-sandbox"
    sandbox_idle_timeout: int = 3600
    sandbox_access_key_id: Optional[str] = None  # 阿里云 AK（控制面 API，自动创建模板）
    sandbox_access_key_secret: Optional[str] = None  # 阿里云 SK
    
    # Supervisor 配置
    supervisor_config: Optional[SupervisorConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        model_value = self.model.value if isinstance(self.model, QwenModel) else str(self.model)
        return {
            "api_key": "***" if self.api_key else None,
            "model": model_value,
            "base_url": self.base_url,
            "use_local_model": self.use_local_model,
            "enable_search": self.enable_search,
            "search_strategy": self.search_strategy,
            "max_concurrent_agents": self.max_concurrent_agents,
            "max_tool_calls": self.max_tool_calls,
            "agent_timeout": self.agent_timeout,
            "complexity_threshold": self.complexity_threshold,
            "enable_long_text_processing": self.enable_long_text_processing,
            "enable_team_mode": self.enable_team_mode,
            "sandbox_account_id": "***" if self.sandbox_account_id else None,
            "sandbox_region_id": self.sandbox_region_id,
            "sandbox_template_name": self.sandbox_template_name,
            "sandbox_idle_timeout": self.sandbox_idle_timeout,
            "sandbox_access_key_id": "***" if self.sandbox_access_key_id else None,
            "sandbox_access_key_secret": "***" if self.sandbox_access_key_secret else None,
            "supervisor_config": {
                "max_react_iterations": self.supervisor_config.max_react_iterations,
                "enable_research": self.supervisor_config.enable_research,
                "enable_quality_gates": self.supervisor_config.enable_quality_gates,
                "quality_threshold": self.supervisor_config.quality_threshold,
                "max_retry_on_failure": self.supervisor_config.max_retry_on_failure,
            } if self.supervisor_config else None,
        }


class AgentSwarm:
    """
    Qwen Agent Swarm 主入口类。
    
    提供简洁的 API 接口，整合所有组件。
    
    Usage:
        swarm = AgentSwarm(api_key="your-api-key")
        result = await swarm.execute("Your complex task here")
    
    Attributes:
        _config: AgentSwarm 配置
        _qwen_client: Qwen 客户端
        _tool_registry: 工具注册表
        _main_agent: 主智能体
        _initialized: 是否已初始化
    """
    
    def __init__(
        self,
        config: Optional[AgentSwarmConfig] = None,
        api_key: Optional[str] = None,
    ):
        """
        初始化 AgentSwarm。
        
        Args:
            config: AgentSwarm 配置
            api_key: API 密钥（快捷方式，会覆盖 config 中的设置）
        """
        self._config = config or AgentSwarmConfig()
        
        if api_key:
            self._config.api_key = api_key
        
        self._qwen_client: Optional[IQwenClient] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._context_manager: Optional[ExecutionContextManager] = None
        self._task_decomposer: Optional[TaskDecomposer] = None
        self._agent_scheduler: Optional[AgentScheduler] = None
        self._result_aggregator: Optional[ResultAggregatorImpl] = None
        self._main_agent: Optional[MainAgent] = None
        self._long_text_processor: Optional[LongTextProcessor] = None
        self._supervisor: Optional[Supervisor] = None
        
        self._initialized = False
    
    def _initialize(self) -> None:
        """延迟初始化所有组件。"""
        if self._initialized:
            return
        
        # 延迟导入以避免循环导入
        from ..core.main_agent import MainAgent, MainAgentConfig
        
        qwen_config = QwenConfig(
            model=self._config.model,
            api_key=self._config.api_key,
            base_url=self._config.base_url,
            enable_search=self._config.enable_search,
            search_strategy=self._config.search_strategy,
        )
        
        if self._config.use_local_model:
            self._qwen_client = LocalQwenClient(qwen_config)
        else:
            self._qwen_client = DashScopeClient(qwen_config)
        
        self._tool_registry = ToolRegistry()
        self._register_builtin_tools()
        self._context_manager = ExecutionContextManager()
        
        self._task_decomposer = TaskDecomposer(
            qwen_client=self._qwen_client,
            complexity_threshold=self._config.complexity_threshold,
        )
        
        from ..interfaces.agent_scheduler import SchedulerConfig
        scheduler_config = SchedulerConfig(
            max_concurrent_agents=self._config.max_concurrent_agents,
            max_tool_calls=self._config.max_tool_calls,
            agent_timeout=self._config.agent_timeout,
        )
        
        self._agent_scheduler = AgentScheduler(
            qwen_client=self._qwen_client,
            tool_registry=self._tool_registry,
            context_manager=self._context_manager,
            config=scheduler_config,
        )
        
        self._result_aggregator = ResultAggregatorImpl()
        
        main_agent_config = MainAgentConfig(
            complexity_threshold=self._config.complexity_threshold,
            execution_timeout=self._config.execution_timeout,
            use_team_mode=self._config.enable_team_mode,
        )
        
        team_lifecycle_manager = None
        wave_executor = None
        if self._config.enable_team_mode:
            from ..team_lifecycle import TeamLifecycleManager
            from ..wave_executor import WaveExecutor
            team_lifecycle_manager = TeamLifecycleManager()
            wave_executor = WaveExecutor()
        
        self._main_agent = MainAgent(
            task_decomposer=self._task_decomposer,
            agent_scheduler=self._agent_scheduler,
            result_aggregator=self._result_aggregator,
            context_manager=self._context_manager,
            config=main_agent_config,
            team_lifecycle_manager=team_lifecycle_manager,
            wave_executor=wave_executor,
        )
        
        if self._config.enable_long_text_processing:
            long_text_config = LongTextConfig(model=self._config.model)
            self._long_text_processor = LongTextProcessor(long_text_config)
        
        if self._config.supervisor_config:
            self._supervisor = Supervisor(
                qwen_client=self._qwen_client,
                config=self._config.supervisor_config,
            )
        
        self._initialized = True

    def _register_builtin_tools(self) -> None:
        """注册内置工具到 ToolRegistry。"""
        try:
            from ..tools import create_code_execution_tool
            code_exec_tool = create_code_execution_tool()
            self._tool_registry.register_tool(code_exec_tool)
        except Exception as e:
            logger.warning(f"code_execution 工具注册失败: {e}")
        
        try:
            from ..tools import create_file_operations_tool
            file_ops_tool = create_file_operations_tool()
            self._tool_registry.register_tool(file_ops_tool)
        except Exception as e:
            logger.warning(f"file_operations 工具注册失败: {e}")
        
        try:
            from ..tools import create_code_review_tool
            code_review_tool = create_code_review_tool()
            self._tool_registry.register_tool(code_review_tool)
        except Exception as e:
            logger.warning(f"code_review 工具注册失败: {e}")
        
        try:
            from ..tools import create_data_analysis_tool
            data_analysis_tool = create_data_analysis_tool()
            self._tool_registry.register_tool(data_analysis_tool)
        except Exception as e:
            logger.warning(f"data_analysis 工具注册失败: {e}")
        
        # 注册沙箱代码解释器（为非 Qwen 模型的 coder/analyst 提供代码执行能力）
        try:
            from ..tools import create_sandbox_code_interpreter_tool
            sandbox_tool = create_sandbox_code_interpreter_tool(
                account_id=self._config.sandbox_account_id,
                region_id=self._config.sandbox_region_id,
                template_name=self._config.sandbox_template_name,
                sandbox_idle_timeout=self._config.sandbox_idle_timeout,
                access_key_id=self._config.sandbox_access_key_id,
                access_key_secret=self._config.sandbox_access_key_secret,
            )
            self._tool_registry.register_tool(sandbox_tool)
        except Exception as e:
            logger.warning(f"sandbox_code_interpreter 工具注册失败: {e}")
        
        # 注册沙箱浏览器（为非 Qwen 模型的 searcher/researcher 等提供网页浏览能力）
        try:
            from ..tools import create_sandbox_browser_tool
            browser_tool = create_sandbox_browser_tool(
                account_id=self._config.sandbox_account_id,
                region_id=self._config.sandbox_region_id,
                sandbox_idle_timeout=self._config.sandbox_idle_timeout,
                access_key_id=self._config.sandbox_access_key_id,
                access_key_secret=self._config.sandbox_access_key_secret,
            )
            self._tool_registry.register_tool(browser_tool)
        except Exception as e:
            logger.warning(f"sandbox_browser 工具注册失败: {e}")
    
    async def execute(
        self,
        task_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> TaskResult:
        """
        执行任务。
        
        Args:
            task_content: 任务内容描述
            metadata: 可选的任务元数据
            stream_callback: 可选的流式回调，用于观察 Supervisor 规划过程
            
        Returns:
            任务执行结果
        """
        import time
        import uuid

        self._initialize()

        if self._supervisor is not None:
            try:
                plan_start = time.monotonic()
                plan = await self._supervisor.plan_task(task_content, metadata, stream_callback)
                plan_elapsed = time.monotonic() - plan_start
            except Exception as e:
                # Supervisor planning failed – fall back to original flow
                logger.error(f"Supervisor 规划失败，回退到原有流程: {e}")
                task = await self._main_agent.submit_task(task_content, metadata)
                result = await self._main_agent.execute_with_timeout(task)
                if result.metadata is None:
                    result.metadata = {}
                result.metadata["supervisor_planning_error"] = str(e)
                return result

            task_analysis = plan.task_analysis
            if (
                task_analysis.get("task_type") == "simple_direct"
                and task_analysis.get("direct_answer")
            ):
                return TaskResult(
                    task_id="",
                    success=True,
                    output=task_analysis["direct_answer"],
                    error=None,
                    execution_time=plan_elapsed,
                    metadata={"task_plan": plan.to_dict()},
                )

            # Non-simple task: use execute_with_plan() with the Supervisor plan
            task = Task(
                id=str(uuid.uuid4()),
                content=plan.refined_task,
                status=TaskStatus.PENDING,
                complexity_score=plan.estimated_complexity,
                created_at=time.time(),
                metadata=metadata or {},
            )
            result = await self._main_agent._executor.execute_with_plan(
                task,
                plan,
                supervisor=self._supervisor,
                stream_callback=stream_callback,
            )
            if result.metadata is None:
                result.metadata = {}
            result.metadata["task_plan"] = plan.to_dict()
            return result

        # No supervisor configured – original flow, ignore stream_callback
        task = await self._main_agent.submit_task(task_content, metadata)
        result = await self._main_agent.execute_with_timeout(task)
        return result
    
    async def submit_task(
        self,
        task_content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """提交任务（不立即执行）。"""
        self._initialize()
        return await self._main_agent.submit_task(task_content, metadata)
    
    async def execute_task(self, task: Task) -> TaskResult:
        """执行已提交的任务。"""
        self._initialize()
        return await self._main_agent.execute_with_timeout(task)
    
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """获取任务状态。"""
        self._initialize()
        return await self._main_agent.get_task_status(task_id)
    
    async def get_progress(self, task_id: str) -> Dict[str, Any]:
        """获取任务执行进度。"""
        self._initialize()
        return await self._main_agent.get_execution_progress(task_id)
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务。"""
        self._initialize()
        return await self._main_agent.cancel_task(task_id)
    
    async def get_summary(self, task_id: str) -> Dict[str, Any]:
        """获取任务执行摘要。"""
        self._initialize()
        return await self._main_agent.generate_execution_summary(task_id)
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具。"""
        self._initialize()
        self._tool_registry.register_tool(tool)
    
    def unregister_tool(self, tool_name: str) -> bool:
        """注销工具。"""
        self._initialize()
        return self._tool_registry.unregister_tool(tool_name)
    
    def list_tools(self) -> List[ToolDefinition]:
        """列出所有已注册的工具。"""
        self._initialize()
        return self._tool_registry.list_tools()
    
    async def get_resource_usage(self) -> Dict[str, Any]:
        """获取资源使用情况。"""
        self._initialize()
        return await self._agent_scheduler.get_resource_usage()
    
    async def shutdown(self) -> Dict[str, Any]:
        """关闭 AgentSwarm。"""
        if not self._initialized:
            return {"status": "not_initialized"}
        # 清理沙箱代码解释器资源
        try:
            from ..tools import cleanup_sandbox
            await cleanup_sandbox()
        except Exception as e:
            logger.warning(f"沙箱清理失败: {e}")
        # 清理浏览器沙箱资源
        try:
            from ..tools import cleanup_browser
            await cleanup_browser()
        except Exception as e:
            logger.warning(f"浏览器沙箱清理失败: {e}")
        return await self._main_agent.graceful_shutdown()
    
    def needs_chunking(self, text: str) -> bool:
        """检测文本是否需要分块处理。"""
        self._initialize()
        if self._long_text_processor:
            return self._long_text_processor.needs_chunking(text)
        return False
    
    def get_text_info(self, text: str) -> Dict[str, Any]:
        """获取文本信息。"""
        self._initialize()
        if self._long_text_processor:
            return self._long_text_processor.get_text_info(text)
        return {"error": "Long text processing not enabled"}
    
    @property
    def config(self) -> AgentSwarmConfig:
        """获取配置。"""
        return self._config
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化。"""
        return self._initialized
    
    @property
    def main_agent(self) -> Optional["MainAgent"]:
        """获取主智能体。"""
        return self._main_agent
    
    @property
    def tool_registry(self) -> Optional[ToolRegistry]:
        """获取工具注册表。"""
        return self._tool_registry
    
    @property
    def qwen_client(self) -> Optional[IQwenClient]:
        """获取 Qwen 客户端。"""
        return self._qwen_client
    
    @property
    def execution_mode(self) -> str:
        """获取当前执行模式。"""
        return 'team' if self._config.enable_team_mode else 'scheduler'
    
    def set_execution_mode(self, mode: str) -> None:
        """运行时切换执行模式。"""
        if mode not in ('scheduler', 'team'):
            raise ValueError(f"Invalid mode: {mode}. Must be 'scheduler' or 'team'")
        
        enable_team = (mode == 'team')
        
        if enable_team and self._main_agent is not None:
            if (self._main_agent._team_lifecycle_manager is None
                    or self._main_agent._wave_executor is None):
                from ..team_lifecycle import TeamLifecycleManager
                from ..wave_executor import WaveExecutor
                self._main_agent._team_lifecycle_manager = TeamLifecycleManager()
                self._main_agent._wave_executor = WaveExecutor()
        
        self._config.enable_team_mode = enable_team
        if self._main_agent is not None:
            self._main_agent._config.use_team_mode = enable_team
