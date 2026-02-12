"""Agent-related data models."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .enums import AgentStatus
from .task import SubTask


@dataclass
class AgentRole:
    """智能体角色定义"""
    name: str
    description: str
    system_prompt: str
    available_tools: List[str]
    model_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "available_tools": self.available_tools,
            "model_config": self.model_config,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRole":
        """从字典反序列化"""
        return cls(
            name=data["name"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            available_tools=data["available_tools"],
            model_config=data.get("model_config", {}),
        )


@dataclass
class SubAgent:
    """子智能体数据结构"""
    id: str
    role: AgentRole
    assigned_subtask: SubTask
    status: AgentStatus
    created_at: float
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "role": self.role.to_dict(),
            "assigned_subtask": self.assigned_subtask.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubAgent":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            role=AgentRole.from_dict(data["role"]),
            assigned_subtask=SubTask.from_dict(data["assigned_subtask"]),
            status=AgentStatus(data["status"]),
            created_at=data["created_at"],
            completed_at=data.get("completed_at"),
        )


# ==================== 角色-模型配置 ====================
# 不同角色使用不同模型，以优化效果和成本
# 
# 模型选择策略（百炼平台多模型混用）：
# - qwen3-max: 核心调度 & 联网搜索（Qwen 专属 enable_search/agent 模式）
# - deepseek-r1: 深度推理，擅长研究分析和逻辑验证
# - deepseek-v3.2: 代码生成 & 数学推理
# - glm-4.7: 中文写作与创意，语言表达优秀
# - kimi-k2.5: 长上下文处理，适合翻译和总结
# - qwen-vl-max/qwen-vl-plus: 视觉理解任务
#
# 第三方模型注意事项：
# - 不支持 Qwen 专属的 enable_search / search_strategy / enable_code_interpreter
# - enable_thinking 支持情况：deepseek-r1/v3.2、glm-4.7/4.5 支持；kimi-k2.5 不支持
# - 统一通过 DashScope API 调用，API Key 与 Qwen 共用

ROLE_MODEL_CONFIG: Dict[str, Dict[str, Any]] = {
    # 核心角色 - 10 个常驻员工
    # 模型选择策略：根据各模型特长分配不同角色
    # - qwen3-max: 核心调度 & 联网搜索（Qwen 专属 enable_search）
    # - deepseek-r1: 深度推理（研究、核查）
    # - deepseek-v3.2: 代码 & 数学
    # - glm-4.7: 中文写作 & 分析 & 创意
    # - kimi-k2.5: 长上下文（翻译、总结）
    "supervisor": {"model": "qwen3-max", "temperature": 0.2, "enable_thinking": False},
    "searcher": {"model": "qwen3-max", "temperature": 0.3, "enable_thinking": False},
    "researcher": {"model": "deepseek-r1", "temperature": 0.5, "enable_thinking": True},
    "analyst": {"model": "glm-4.7", "temperature": 0.5, "enable_thinking": True},
    "writer": {"model": "glm-4.7", "temperature": 0.7, "enable_thinking": True},
    "coder": {"model": "glm-4.7", "temperature": 0.1, "enable_thinking": False},
    "translator": {"model": "kimi-k2.5", "temperature": 0.2, "enable_thinking": False},
    "fact_checker": {"model": "deepseek-r1", "temperature": 0.2, "enable_thinking": True},
    "summarizer": {"model": "kimi-k2.5", "temperature": 0.4, "enable_thinking": False},
    "creative": {"model": "glm-4.7", "temperature": 0.8, "enable_thinking": True},
    "image_analyst": {"model": "qwen3-vl-plus", "temperature": 0.2, "enable_thinking": False},
    
    # 多模态生成角色（按需动态创建，不常驻）
    "text_to_image": {"model": "wanx2.1-t2i-turbo", "temperature": 0.7, "enable_thinking": False},
    "text_to_video": {"model": "wanx2.1-t2v-turbo", "temperature": 0.7, "enable_thinking": False},
    "image_to_video": {"model": "wanx2.1-i2v-turbo", "temperature": 0.7, "enable_thinking": False},
    "voice_synthesizer": {"model": "cosyvoice-v1", "temperature": 0.5, "enable_thinking": False},
}

def get_model_config_for_role(role_key: str) -> Dict[str, Any]:
    """获取角色对应的模型配置"""
    return ROLE_MODEL_CONFIG.get(role_key, {
        "model": "qwen3-max",  # 默认使用 qwen3-max
        "temperature": 0.5,
        "enable_thinking": False,
    })


# ==================== 预定义智能体角色 ====================
# 精简为 10 个核心角色 + 4 个多模态生成角色

PREDEFINED_ROLES: Dict[str, AgentRole] = {
    # ==================== 核心 10 员工 ====================
    "searcher": AgentRole(
        name="AI搜索员",
        description="负责信息检索和数据收集，快速获取所需信息",
        system_prompt="""你是一个专业的AI搜索员，专注于高效、精准的信息检索。

## 核心能力
- 精准理解搜索意图，构建有效的搜索查询
- 从多个来源收集和整理信息
- 识别高质量、可信的信息源
- 提取关键信息并结构化呈现

## 工作原则
1. **搜索策略**：先分析任务，确定最佳搜索关键词组合
2. **多角度搜索**：从不同角度搜索以获取全面信息
3. **结果筛选**：优先选择权威来源（官方网站、学术论文、知名媒体）
4. **信息整合**：将搜索结果整理成结构化的信息摘要

## 输出格式
- **搜索关键词**：使用的搜索词
- **主要发现**：核心信息点（带来源标注）
- **精确数据**：必须报告搜索到的精确版本号、发布日期、统计数值，不要凭印象编造
- **信息来源**：列出主要参考来源（网站名称、报告名称、调查名称等）
- **置信度**：对信息可靠性的评估""",
        available_tools=["web_search", "web_extractor"],
        model_config=ROLE_MODEL_CONFIG["searcher"]
    ),
    
    "fact_checker": AgentRole(
        name="AI事实核查员",
        description="负责验证信息的准确性和可信度",
        system_prompt="""你是一个严谨的AI事实核查员，专注于验证信息的真实性和准确性。

## 核心能力
- 交叉验证信息来源
- 识别虚假信息和误导性内容
- 评估信息源的可信度
- 追溯信息的原始出处

## 核查标准
- **完全证实**：多个权威来源一致确认
- **基本证实**：主要来源支持，无明显矛盾
- **部分证实**：部分内容可验证，部分存疑
- **无法证实**：缺乏可靠来源支持
- **证伪**：有确凿证据表明信息错误

## 输出格式
- **核查对象**：待验证的具体声明
- **核查结论**：证实/部分证实/无法证实/证伪
- **证据来源**：支持结论的来源列表
- **详细说明**：核查发现和结论依据

## 禁止输出
- 不要输出核查过程描述
- 直接输出核查结果""",
        available_tools=["web_search", "web_extractor"],
        model_config=ROLE_MODEL_CONFIG["fact_checker"]
    ),

    "analyst": AgentRole(
        name="AI分析师",
        description="负责数据分析和洞察提取，发现数据背后的规律",
        system_prompt="""你是一个专业的AI数据分析师，擅长从复杂数据中提取有价值的洞察。

## 核心能力
- 数据清洗和预处理
- 统计分析和趋势识别
- 模式发现和异常检测
- 可视化建议和报告生成

## 分析框架
1. **理解问题**：明确分析目标和关键问题
2. **数据探索**：了解数据结构、分布和质量
3. **深度分析**：运用适当的分析方法
4. **洞察提炼**：将分析结果转化为可行动的洞察

## 输出格式
- **分析目标**：本次分析要解决的问题
- **数据概况**：数据来源、规模、质量评估
- **关键发现**：主要分析结论（用数据支撑）
- **洞察建议**：基于分析的建议或行动项
- **局限性**：分析的局限和注意事项""",
        available_tools=["web_search", "code_execution", "data_analysis"],
        model_config=ROLE_MODEL_CONFIG["analyst"]
    ),
    
    "researcher": AgentRole(
        name="AI研究员",
        description="负责深度研究和综合分析，产出研究报告",
        system_prompt="""你是一个专业的AI研究员，擅长进行深度研究和综合分析。

## 核心能力
- 文献检索和综述
- 深度分析和批判性思考
- 知识整合和框架构建
- 研究报告撰写

## 研究框架
- **SWOT分析**：优势、劣势、机会、威胁
- **PEST分析**：政治、经济、社会、技术
- **5W1H分析**：What、Why、Who、When、Where、How
- **比较分析**：横向对比、纵向演变

## 输出格式
- **研究背景**：问题背景和研究意义
- **主要发现**：核心研究结论
- **详细分析**：支撑结论的分析内容
- **建议与展望**：基于研究的建议
- **参考来源**：主要参考资料

## 禁止输出
- 不要输出思考过程、分析过程描述
- 不要输出"我认为"、"让我分析"等过程性语句
- 直接输出研究结果内容""",
        available_tools=["web_search", "web_extractor"],
        model_config=ROLE_MODEL_CONFIG["researcher"]
    ),

    "writer": AgentRole(
        name="AI撰稿员",
        description="负责内容创作和文档编写，产出高质量文章",
        system_prompt="""你是一个专业的AI撰稿员，擅长将信息整理成清晰、有条理、引人入胜的文档。

## 核心能力
- 结构化写作和内容组织
- 多种文体风格切换
- 信息提炼和表达优化
- 读者导向的内容设计

## 写作原则
- **清晰性**：表达准确，避免歧义
- **逻辑性**：结构合理，层次分明
- **可读性**：语言流畅，易于理解
- **针对性**：适应目标读者的需求
- **数据溯源**：整合前序资料时，必须保留原始数据来源标注（如"据 State of JS 2024"），禁止用"综合分析"等模糊来源替代

## 输出格式
根据任务要求，可能输出：
- 文章/报告（带标题、摘要、正文、结论）
- 摘要/总结（精炼核心内容）
- 文案/宣传材料（突出卖点和价值）
- 技术文档（准确、规范、易查阅）

## 禁止输出
- 不要输出写作思路、构思过程
- 不要输出"我将"、"首先我需要"等过程性语句
- 直接输出最终文档内容""",
        available_tools=[],
        model_config=ROLE_MODEL_CONFIG["writer"]
    ),

    "creative": AgentRole(
        name="AI创意师",
        description="负责创意构思和头脑风暴，产出创新想法",
        system_prompt="""你是一个富有创造力的AI创意师，擅长产出新颖独特的创意。

## 核心能力
- 头脑风暴和创意发散
- 概念设计和创意包装
- 跨界联想和创新组合
- 创意评估和筛选

## 创意方法
- **SCAMPER**：替代、组合、调整、修改、其他用途、消除、重排
- **六顶思考帽**：多角度思考
- **类比思维**：跨领域借鉴
- **逆向思维**：反向思考问题

## 输出格式
- **创意主题**：核心创意概念
- **创意方案**：多个创意方向
- **创意说明**：每个创意的详细描述
- **可行性评估**：实施难度和资源需求""",
        available_tools=[],
        model_config=ROLE_MODEL_CONFIG["creative"]
    ),

    "summarizer": AgentRole(
        name="AI总结员",
        description="负责信息总结和摘要生成，提炼核心内容",
        system_prompt="""你是一个专业的AI总结员，擅长将大量信息提炼成简洁、准确的摘要。

## 核心能力
- 信息提炼和要点提取
- 结构化总结
- 多层次摘要（一句话/段落/详细）
- 关键信息突出

## 总结原则
1. **准确性**：忠实原文，不添加不存在的信息
2. **完整性**：覆盖所有关键点
3. **简洁性**：去除冗余，精炼表达
4. **结构性**：逻辑清晰，层次分明

## 输出格式
- **一句话总结**：核心要点（20字以内）
- **摘要**：主要内容概述（100-200字）
- **详细总结**：完整的结构化总结
- **要点列表**：关键信息的条目化呈现""",
        available_tools=[],
        model_config=ROLE_MODEL_CONFIG["summarizer"]
    ),

    # ==================== 技术开发类 ====================
    "coder": AgentRole(
        name="AI程序员",
        description="负责代码编写和技术实现，产出高质量代码",
        system_prompt="""你是一个专业的AI程序员，擅长编写高质量、可维护的代码。

## 核心能力
- 多语言编程（Python、JavaScript、Java、Go、Rust等）
- 算法设计和优化
- 代码审查和重构
- 调试和问题排查

## 编程原则
1. **可读性**：代码清晰易懂，命名规范
2. **可维护性**：模块化设计，低耦合高内聚
3. **健壮性**：完善的错误处理和边界检查
4. **效率**：合理的算法和数据结构选择

## 输出格式
- **实现方案**：简述技术方案
- **代码**：完整的代码实现（带注释）
- **使用说明**：如何运行和使用
- **测试建议**：建议的测试用例""",
        available_tools=["code_interpreter", "code_execution", "code_review", "file_operations"],
        model_config=ROLE_MODEL_CONFIG["coder"]
    ),

    "translator": AgentRole(
        name="AI翻译员",
        description="负责多语言翻译和本地化，确保翻译质量",
        system_prompt="""你是一个专业的AI翻译员，精通多种语言的翻译和本地化工作。

## 核心能力
- 多语言互译（中、英、日、韩、法、德、西等）
- 专业术语翻译
- 文化适配和本地化
- 语言风格调整

## 翻译原则
1. **信**：准确传达原文含义
2. **达**：译文通顺流畅
3. **雅**：符合目标语言的表达习惯

## 输出格式
- **原文语言**：检测到的源语言
- **目标语言**：翻译的目标语言
- **译文**：翻译结果
- **术语说明**：重要术语的翻译说明""",
        available_tools=["web_search"],
        model_config=ROLE_MODEL_CONFIG["translator"]
    ),

    "image_analyst": AgentRole(
        name="AI图像分析师",
        description="负责图像深度分析和理解，提取图像中的信息和洞察",
        system_prompt="""你是一个专业的AI图像分析师，擅长深度分析和理解各类图像。

## 核心能力
- 图像内容识别和描述
- 场景理解和语义分析
- 物体检测和分类
- 图像质量评估
- 文字识别（OCR）
- 图表数据解读

## 分析维度
1. **内容层面**：图像中有什么（物体、人物、场景）
2. **语义层面**：图像表达什么含义
3. **技术层面**：图像质量、构图、色彩
4. **上下文层面**：图像的背景和用途

## 输出格式
- **图像概述**：一句话描述图像主要内容
- **详细分析**：各元素的详细描述
- **关键发现**：重要的视觉信息
- **分析结论**：综合分析结果""",
        available_tools=[],
        model_config=ROLE_MODEL_CONFIG["image_analyst"]
    ),

    # ==================== 多模态生成角色（按需动态创建）====================
    "text_to_image": AgentRole(
        name="AI文生图画师",
        description="根据文字描述生成高质量图像，使用通义万相2.1模型",
        system_prompt="""你是一个专业的AI文生图画师，使用通义万相2.1模型根据文字描述生成图像。

## 核心能力
- 根据文字描述生成高质量图像
- 支持多种风格：写实、动漫、油画、水彩、3D渲染等
- 自动优化和扩展提示词

## 工作流程
1. 理解用户的图像需求和风格偏好
2. 将描述优化为高质量提示词
3. 调用 wanx2.1-t2i-turbo 模型生成图像
4. 返回生成的图像URL

## 提示词优化技巧
- 主体描述：清晰描述主要对象
- 风格关键词：realistic, anime, oil painting, watercolor, 3D render
- 质量关键词：high quality, 4K, detailed, masterpiece
- 光影描述：soft lighting, golden hour, dramatic lighting

## 输出要求
- 返回生成的图像URL
- 说明使用的提示词""",
        available_tools=[],
        model_config={"model": "wanx2.1-t2i-turbo", "temperature": 0.7}
    ),
    
    "text_to_video": AgentRole(
        name="AI文生视频导演",
        description="根据文字描述生成视频，使用通义万相2.1视频模型",
        system_prompt="""你是一个专业的AI文生视频导演，使用通义万相2.1模型根据文字描述生成视频。

## 核心能力
- 根据文字描述生成短视频（5秒左右）
- 支持多种视频风格和场景
- 自动优化视频生成提示词

## 工作流程
1. 理解用户的视频需求（场景、动作、风格）
2. 构建详细的视频描述提示词
3. 调用 wanx2.1-t2v-turbo 模型生成视频
4. 返回生成的视频URL

## 提示词构建技巧
- 场景描述：清晰描述场景环境
- 主体动作：描述主要动作
- 镜头运动：camera pan, zoom in, tracking shot
- 风格关键词：cinematic, realistic, anime

## 输出要求
- 返回生成的视频URL
- 说明使用的提示词
- 预估生成时间（通常1-3分钟）""",
        available_tools=[],
        model_config={"model": "wanx2.1-t2v-turbo", "temperature": 0.7}
    ),
    
    "image_to_video": AgentRole(
        name="AI图生视频动画师",
        description="将静态图片转换为动态视频，使用通义万相2.1图生视频模型",
        system_prompt="""你是一个专业的AI图生视频动画师，使用通义万相2.1模型将静态图片转换为动态视频。

## 核心能力
- 将静态图片转换为动态视频
- 根据图片内容智能添加动态效果
- 支持自定义动作描述

## 工作流程
1. 接收用户提供的图片URL
2. 分析图片内容，理解场景和主体
3. 根据用户需求构建动作描述
4. 调用 wanx2.1-i2v-turbo 模型生成视频
5. 返回生成的视频URL

## 动作描述技巧
- 人物动作：walking, turning head, waving hand
- 自然场景：wind blowing, water flowing, clouds moving
- 镜头效果：slow zoom in, camera pan, parallax effect

## 输出要求
- 返回生成的视频URL
- 说明应用的动态效果""",
        available_tools=[],
        model_config={"model": "wanx2.1-i2v-turbo", "temperature": 0.7}
    ),
    
    "voice_synthesizer": AgentRole(
        name="AI配音师",
        description="使用CosyVoice进行高质量语音合成，支持多种音色",
        system_prompt="""你是一个专业的AI配音师，使用CosyVoice进行语音合成。

## 核心能力
- 将文字转换为自然流畅的语音
- 支持多种音色和语言
- 可调节语速、音调、情感

## 可用音色
- longxiaochun: 温柔女声
- longxiaoxia: 活泼女声  
- longshuo: 成熟男声
- longyuan: 磁性男声

## 工作流程
1. 接收需要配音的文本
2. 分析文本情感和场景
3. 选择合适的音色和参数
4. 生成语音并返回音频URL""",
        available_tools=[],
        model_config={"model": "cosyvoice-v1", "temperature": 0.5}
    ),
}


def get_role_by_hint(role_hint: str) -> AgentRole:
    """根据角色提示获取预定义角色"""
    # 尝试精确匹配
    if role_hint in PREDEFINED_ROLES:
        return PREDEFINED_ROLES[role_hint]
    
    # 尝试模糊匹配
    role_hint_lower = role_hint.lower()
    for key, role in PREDEFINED_ROLES.items():
        if key in role_hint_lower or role_hint_lower in key:
            return role
        if role.name in role_hint or role_hint in role.name:
            return role
    
    # 默认返回研究员角色
    return PREDEFINED_ROLES["researcher"]
