<p align="center">
  <h1 align="center">Qwen Agent Swarm</h1>
  <p align="center">
    Multi-agent orchestration framework powered by Qwen LLMs — with multi-model routing via Alibaba Cloud DashScope.<br/>
    基于通义千问大模型的多智能体编排框架，通过百炼平台实现多模型混合调度。
  </p>
</p>

<p align="center">
  <a href="#项目简介">项目简介</a> •
  <a href="#核心特性">核心特性</a> •
  <a href="#架构">架构</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#配置">配置</a> •
  <a href="#web-dashboard">Web Dashboard</a> •
  <a href="#开发">开发</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha">
</p>

---

## 项目简介

Turn a single sentence into a coordinated AI team effort — automatic task decomposition, multi-model role assignment, parallel execution, quality gate review, and result aggregation.

把一句话需求交给一整个 AI 团队 — 自动拆解任务、多模型角色分配、并行执行、质量门控评审、汇总结果。

## 核心特性

- **Supervisor (ReAct)** — Analyzes intent, researches context, rewrites requirements, creates execution plans, and reviews each stage output through quality gates
- **Task Decomposition** — Breaks complex tasks into a dependency-aware DAG of subtasks with topological execution ordering
- **Multi-Model Routing** — Routes each role to the best-fit model: Qwen3 for search, DeepSeek R1 for reasoning, GLM-4.7 for writing, Kimi K2.5 for long context, Qwen-VL for vision — all through a single DashScope API key
- **Parallel Sub-Agents** — Up to 100 concurrent agents with 1,500 tool calls per task, each with role-specific system prompts and tool access
- **Quality Gate Review** — Stage-level quality scoring with dynamic flow adjustment: continue, retry, add compensating steps, or skip
- **Supervisor SDK Integration** — Optional Supervisor planning stage in `AgentSwarm.execute()` for SDK users, with task rewriting, execution plan generation, simple task direct answer, and quality gates — fully backward compatible
- **Multimodal Generation** — Text-to-image (Wanx 2.1), text-to-video, image-to-video, and voice synthesis (CosyVoice) as on-demand agent roles
- **Long Text Processing** — Automatic chunking and merging for inputs exceeding model context limits
- **Result Aggregation** — Merges outputs from multiple agents, resolves conflicts, produces typed deliverables (report, code, website, image, video, dataset, document, composite)
- **Web Dashboard** — Real-time visualization of task flow, agent status, and execution logs via WebSocket

## 架构

```
User Input
    ↓
Supervisor (ReAct: analyze → research → rewrite → plan)
    ↓
TaskDecomposer → DAG of SubTasks with dependencies
    ↓
AgentScheduler (topological sort → wave-based parallel dispatch)
    ↓
SubAgent × N (parallel, each with role-specific model & tools)
    ↓                          ↑
QualityGateReviewer ──────────┘  (retry / add_step / skip_next)
    ↓
ResultAggregator → conflict resolution → typed output
    ↓
OutputHandler (report / code / website / image / video / composite)
    ↓
Final Output
```

### SDK 执行流程（启用 Supervisor）

```
AgentSwarm.execute(task_content, metadata, stream_callback)
    ↓
supervisor_config 存在?
    ├─ 否 → 原有流程 (submit_task → execute_with_timeout)
    └─ 是 → Supervisor.plan_task()
              ↓
         simple_direct? ──是──→ 直接返回 TaskResult(direct_answer)
              ↓ 否
         TaskExecutor.execute_with_plan(task, plan, supervisor)
              ↓
         ExecutionFlow → SubTask 转换 → WaveExecutor 执行
              ↓
         质量门控 (evaluate_step_result → retry / add_step / continue)
              ↓
         TaskResult (metadata 包含 task_plan)
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（仅 Web Dashboard 需要）
- [DashScope API key](https://dashscope.console.aliyun.com/)（阿里云百炼平台）

### 安装

```bash
git clone https://github.com/your-org/qwen-agent-swarm.git
cd qwen-agent-swarm
python -m venv .venv && source .venv/bin/activate
pip install -e .          # SDK only
pip install -e ".[web]"   # SDK + Web Dashboard 依赖
pip install -e ".[all]"   # 全部依赖（含开发工具）
```

### 基本用法

```python
import asyncio
from src import AgentSwarm, AgentSwarmConfig

async def main():
    swarm = AgentSwarm(config=AgentSwarmConfig(
        api_key="your-dashscope-api-key",   # or set DASHSCOPE_API_KEY env var
        enable_search=True,
    ))
    result = await swarm.execute(
        "Compare React, Vue, and Angular for a 2025 tech stack decision"
    )
    print(result.output if result.success else result.error)
    await swarm.shutdown()

asyncio.run(main())
```

### 启用 Supervisor 规划

```python
from src import AgentSwarm, AgentSwarmConfig, SupervisorConfig

async def main():
    swarm = AgentSwarm(config=AgentSwarmConfig(
        api_key="your-dashscope-api-key",
        supervisor_config=SupervisorConfig(
            enable_quality_gates=True,
            max_retry_on_failure=2,
        ),
    ))

    # stream_callback 可选，用于观察规划过程
    async def on_stream(text: str):
        print(text, end="", flush=True)

    result = await swarm.execute(
        "分析 2025 年最值得学习的三个编程语言",
        stream_callback=on_stream,
    )
    print(result.output)

    # 访问规划详情
    if result.metadata and "task_plan" in result.metadata:
        print(result.metadata["task_plan"])

    await swarm.shutdown()
```

### Core API

```python
# One-shot execution
result = await swarm.execute("Your task description")

# With Supervisor planning + stream callback
result = await swarm.execute("Your task", stream_callback=my_callback)

# Step-by-step control
task = await swarm.submit_task("Your task description")
result = await swarm.execute_task(task)

# Progress & lifecycle
progress = await swarm.get_progress(task.id)
summary = await swarm.get_summary(task.id)
await swarm.cancel_task(task.id)

# Tool management
swarm.register_tool(my_tool)
swarm.unregister_tool("my_tool")
tools = swarm.list_tools()

# Runtime mode switching
swarm.set_execution_mode("team")       # team collaboration mode
swarm.set_execution_mode("scheduler")  # scheduler mode
```

## Multi-Model Routing

Each agent role is routed to the model best suited for its task, all through a single DashScope API key:

| Role | Model | Rationale |
|------|-------|-----------|
| Supervisor | qwen3-max | Core orchestration with native search |
| Searcher | qwen3-max | Qwen-exclusive `enable_search` capability |
| Researcher | deepseek-r1 | Deep reasoning and chain-of-thought |
| Analyst | glm-4.7 | Strong Chinese analysis and insight extraction |
| Writer | glm-4.7 | Excellent Chinese prose and structured writing |
| Coder | glm-4.7 | Code generation with sandbox code execution |
| Translator | kimi-k2.5 | Long context window for document translation |
| Fact Checker | deepseek-r1 | Rigorous logical verification |
| Summarizer | kimi-k2.5 | Long context for comprehensive summarization |
| Creative | glm-4.7 | Creative ideation with thinking mode |
| Image Analyst | qwen-vl-max | Multimodal vision understanding |

On-demand multimodal roles:

| Role | Model | Capability |
|------|-------|------------|
| Text-to-Image | wanx2.1-t2i-turbo | Image generation from text prompts |
| Text-to-Video | wanx2.1-t2v-turbo | Video generation from text descriptions |
| Image-to-Video | wanx2.1-i2v-turbo | Animate static images into video |
| Voice Synthesizer | cosyvoice-v1 | Text-to-speech with multiple voice profiles |

> Third-party models (DeepSeek, GLM, Kimi) do not support Qwen-exclusive features like `enable_search` or `enable_code_interpreter`. The framework handles this automatically — see [Sandbox Code Interpreter](#sandbox-code-interpreter) and [Web Search & Browser Tool](#web-search--browser-tool) below.

## Sandbox Code Interpreter

When a sub-agent role (e.g. `coder`, `analyst`) uses a non-Qwen model, DashScope's built-in `code_interpreter` is unavailable. The framework automatically falls back to a cloud sandbox powered by [Alibaba Cloud AgentRun Sandbox](https://help.aliyun.com/zh/functioncompute/fc/sandbox-sandbox-code-interepreter), exposed as a standard function-calling tool (`sandbox_code_interpreter`).

**How it works:**

1. Non-Qwen model agents detect that `code_interpreter` is unavailable
2. A `sandbox_code_interpreter` tool is injected into their tool schema
3. The model calls it like any other function tool → code runs in a cloud sandbox → results return to the model
4. Sandbox templates are auto-created via the control plane API if they don't exist (requires AK/SK)

**Configuration:**

```python
config = AgentSwarmConfig(
    api_key="your-dashscope-key",
    sandbox_account_id="<your-account-id>",           # Alibaba Cloud account ID
    sandbox_access_key_id="<your-access-key-id>",     # AccessKey ID (for template auto-creation)
    sandbox_access_key_secret="<your-access-secret>",  # AccessKey Secret
    sandbox_region_id="cn-hangzhou",                   # Region (default: cn-hangzhou)
    sandbox_template_name="python-sandbox",            # Template name (default: python-sandbox)
    sandbox_idle_timeout=3600,                         # Idle timeout in seconds (default: 3600)
)
```

Or via environment variables:

```bash
export ALIYUN_ACCOUNT_ID=<your-account-id>
export ALIYUN_ACCESS_KEY_ID=<your-access-key-id>
export ALIYUN_ACCESS_KEY_SECRET=<your-access-secret>
```

These can also be configured in the Web Dashboard settings panel.

**Lifecycle & Cleanup:**

- Sandboxes are stopped after each task execution (`finally` block)
- `AgentSwarm.shutdown()` triggers sandbox cleanup
- An `atexit` handler acts as a safety net on process exit
- Sandbox state is persisted to `/tmp/qwen_swarm_sandbox_state.json` — on crash/restart, orphaned sandboxes are cleaned up during FastAPI startup
- Cloud-side `sandboxIdleTimeoutInSeconds` + 6-hour max lifetime provide ultimate fallback

## Web Search & Browser Tool

When sub-agent roles (e.g. `researcher`, `fact_checker`, `analyst`, `translator`) use non-Qwen models, DashScope's built-in `enable_search` / `web_extractor` is unavailable. The framework automatically falls back to a `sandbox_browser` function-calling tool that provides both keyword search and page content extraction via direct HTTP requests.

**Two operation modes:**

| Action | Description |
|--------|-------------|
| `search` | Search keywords via search engine (Quark primary, Bing fallback), returns structured results (title, URL, source) |
| `fetch` | Navigate to a URL and extract page title + text content |

**Typical workflow:** model calls `search` to find relevant pages → picks URLs from results → calls `fetch` to read full content → synthesizes answer.

**Search engine strategy:**

1. **Quark (夸克)** — Primary engine for Chinese mainland. High-quality results from CSDN, Python docs, Zhihu, Juejin, Alibaba Cloud, Tencent Cloud, etc. Built-in CDN retry for connection stability.
2. **Bing (international mode)** — Fallback when Quark is unavailable. Uses `ensearch=1` for international results with real URL extraction from cite tags.

**How it works:**

1. Non-Qwen model agents detect that `web_search` / `web_extractor` is unavailable
2. A `sandbox_browser` tool is injected into their tool schema with `search` and `fetch` actions
3. The model calls it like any other function tool → HTTP request → parsed results return to the model
4. HTML text extraction uses regex pre-stripping of script/style/noscript/svg tags before HTMLParser, handling malformed HTML from complex sites
5. Requests include full browser fingerprint headers (User-Agent, Sec-Fetch-*, etc.) for anti-scraping evasion
6. Connection errors and timeouts trigger automatic retries (up to 2 times)

**No additional configuration required** — the tool works out of the box with direct HTTP requests. No API keys, no cloud sandbox, no Playwright dependency.

## 配置

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | `None` | DashScope API key (or set `DASHSCOPE_API_KEY` env var) |
| `model` | `qwen3-max` | Default Qwen model for supervisor |
| `enable_search` | `True` | Enable web search for Qwen-native agents |
| `search_strategy` | `None` | Search strategy (`None` = basic, `"agent_max"` = with web extraction) |
| `max_concurrent_agents` | `100` | Max concurrent sub-agents |
| `max_tool_calls` | `1500` | Max total tool invocations per task |
| `agent_timeout` | `300s` | Per-agent timeout |
| `execution_timeout` | `3600s` | Overall task timeout |
| `complexity_threshold` | `3.0` | Complexity score threshold for task decomposition |
| `enable_long_text_processing` | `True` | Auto-chunk inputs exceeding model context limits |
| `enable_team_mode` | `False` | Enable team collaboration with wave executor |
| `supervisor_config` | `None` | Optional `SupervisorConfig` to enable Supervisor planning stage |
| `sandbox_account_id` | `None` | Alibaba Cloud account ID for sandbox (or `ALIYUN_ACCOUNT_ID` env var) |
| `sandbox_access_key_id` | `None` | AccessKey ID for auto-creating sandbox templates (or `ALIYUN_ACCESS_KEY_ID`) |
| `sandbox_access_key_secret` | `None` | AccessKey Secret (or `ALIYUN_ACCESS_KEY_SECRET`) |
| `sandbox_region_id` | `cn-hangzhou` | AgentRun Sandbox region |
| `sandbox_template_name` | `python-sandbox` | Sandbox template name |
| `sandbox_idle_timeout` | `3600` | Sandbox idle timeout in seconds |

### SupervisorConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_quality_gates` | `True` | Enable quality gate evaluation after each step |
| `quality_threshold` | `0.7` | Minimum quality score to pass |
| `max_retry_on_failure` | `2` | Max retries when quality gate returns `retry` |
| `max_react_iterations` | `5` | Max ReAct iterations for planning |
| `enable_research` | `True` | Enable background research during planning |

## Built-in Tools

| Tool | Description |
|------|-------------|
| Code Execution | Sandboxed Python execution via RestrictedPython |
| Sandbox Code Interpreter | Cloud sandbox execution via AgentRun (fallback for non-Qwen models) |
| Web Search & Browser | Keyword search (Quark/Bing) + page content extraction (fallback for non-Qwen models) |
| File Operations | File read/write/list operations |
| Code Review | Automated code quality analysis |
| Data Analysis | Statistical analysis and data processing |
| Web Search | Built-in via DashScope `enable_search` (Qwen-native models only) |
| Web Extractor | Built-in via `search_strategy="agent_max"` (Qwen-native models only) |

### 自定义工具

```python
from src.models.tool import ToolDefinition

tool = ToolDefinition(
    name="my_tool",
    description="Custom tool description",
    parameters_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
    },
    handler=my_async_handler,  # must be async
)
swarm.register_tool(tool)
```

## Project Structure

```
├── deploy.sh                # 一键部署脚本（macOS / Linux）
├── pyproject.toml           # 项目配置 & 依赖声明
├── config/agents.json       # Agent 配置
├── src/                     # SDK 源码
│   ├── core/                #   编排层
│   │   ├── agent_swarm.py   #     AgentSwarm 统一入口
│   │   ├── main_agent/      #     MainAgent (submit / execute / monitor / plan)
│   │   ├── supervisor/      #     Supervisor (ReAct) + QualityGateReviewer
│   │   ├── task_decomposer.py #   DAG 任务分解
│   │   └── quality_assurance.py # 多层质量检查
│   ├── execution/           #   执行引擎
│   │   ├── sub_agent/       #     SubAgent 执行单元
│   │   ├── scheduler.py     #     拓扑调度 + 并发控制
│   │   ├── wave_executor.py #     Wave 并行执行器
│   │   └── context_manager.py #   线程安全执行上下文
│   ├── handlers/            #   输出类型处理器
│   ├── models/              #   数据模型 (Task, Agent, Result, Tool, etc.)
│   ├── interfaces/          #   抽象接口定义 (ABC)
│   ├── qwen/                #   Qwen 客户端 (DashScope API + 本地模型)
│   ├── tools/               #   内置工具 + 沙箱后端
│   ├── memory/              #   记忆管理
│   ├── pipeline_optimizer/  #   流水线优化
│   └── utils/               #   日志 & 工具函数
├── web/
│   ├── backend/             #   FastAPI + WebSocket (端口 8000)
│   └── frontend/            #   React + Vite + Tailwind (端口 3000)
└── tests/                   # 测试
```

## Web Dashboard

Real-time task monitoring with WebSocket push.

```bash
# 快速启动（自动安装依赖 + 构建 + 启动）
cd web/backend && pip install -r requirements.txt && python app.py

# 前端开发模式
cd web/frontend && npm install && npm run dev
```

API docs: http://localhost:8000/docs

| Endpoint | Description |
|----------|-------------|
| `POST /api/tasks` | Create task |
| `GET /api/tasks` | List tasks |
| `GET /api/tasks/{id}` | Task details |
| `GET /api/tasks/{id}/flow` | Execution flow graph |
| `DELETE /api/tasks/{id}` | Cancel task |
| `GET /api/agents` | List agents |
| `GET /api/stats` | Platform stats |
| `GET /api/config/sandbox` | Get sandbox config |
| `POST /api/config/sandbox` | Update sandbox config (account ID, AK/SK) |
| `WS /ws` | Real-time event push |

## 部署

### 一键部署（推荐）

```bash
chmod +x deploy.sh
./deploy.sh              # 完整部署：检查依赖 → 安装 → 构建前端 → 启动服务
```

支持 macOS / Ubuntu / Debian / CentOS / RHEL，脚本会自动检测系统并安装缺失的 Python、Node.js 等依赖。

首次部署后会在 `web/backend/.env` 生成配置模板，需要填入 `DASHSCOPE_API_KEY`。

### 服务管理

```bash
./deploy.sh --start      # 启动服务
./deploy.sh --stop       # 停止服务
./deploy.sh --restart    # 重启服务
./deploy.sh --status     # 查看运行状态
./deploy.sh --logs       # 查看日志
./deploy.sh --build      # 仅构建前端
./deploy.sh --sdk        # 仅安装 SDK（不启动 Web 服务）
```

### Docker 部署

```bash
./deploy.sh --docker     # 生成 Dockerfile + docker-compose.yml

# 编辑 web/backend/.env 填入 API Key，然后：
docker compose up -d
```

### Systemd 服务（Linux 生产环境）

```bash
./deploy.sh --systemd    # 安装并启用开机自启
sudo systemctl start qwen-swarm-backend qwen-swarm-frontend
```

### 端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| 后端 API | 8000 | FastAPI + WebSocket |
| 前端 | 3000 | React SPA (生产模式由 serve 托管) |

## 开发

```bash
pip install -e ".[dev]"

pytest                # Run tests
mypy src/             # Type checking
ruff check src/       # Linting
ruff format src/      # Formatting
```

### Backward Compatibility

Refactored modules retain compatibility import layers at their original paths:

```python
# Recommended
from src.core.main_agent import MainAgent
from src.core.agent_swarm import AgentSwarm

# Legacy (still works)
from src.main_agent import MainAgent
from src.agent_swarm import AgentSwarm
```

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

[MIT](LICENSE)
