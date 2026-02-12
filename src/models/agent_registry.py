"""
AI 员工注册系统
支持动态注册、解雇员工，以及多模态能力（文本、图像生成、语音等）
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import json
import os


class AgentCapability(Enum):
    """智能体能力类型"""
    # 文本能力
    TEXT_GENERATION = "text_generation"      # 文本生成
    TEXT_ANALYSIS = "text_analysis"          # 文本分析
    TEXT_TRANSLATION = "text_translation"    # 文本翻译
    
    # 视觉能力
    IMAGE_UNDERSTANDING = "image_understanding"  # 图像理解
    IMAGE_GENERATION = "image_generation"        # 图像生成 (wanx)
    IMAGE_EDITING = "image_editing"              # 图像编辑
    OCR = "ocr"                                   # 文字识别
    
    # 语音能力
    SPEECH_TO_TEXT = "speech_to_text"        # 语音转文字
    TEXT_TO_SPEECH = "text_to_speech"        # 文字转语音 (tts)
    VOICE_CLONE = "voice_clone"              # 声音克隆
    
    # 视频能力
    VIDEO_UNDERSTANDING = "video_understanding"  # 视频理解
    VIDEO_GENERATION = "video_generation"        # 视频生成
    
    # 代码能力
    CODE_GENERATION = "code_generation"      # 代码生成
    CODE_EXECUTION = "code_execution"        # 代码执行
    
    # 搜索能力
    WEB_SEARCH = "web_search"                # 网络搜索
    DOCUMENT_SEARCH = "document_search"      # 文档搜索


class AgentType(Enum):
    """智能体类型"""
    TEXT = "text"           # 纯文本智能体
    VISION = "vision"       # 视觉智能体
    AUDIO = "audio"         # 音频智能体
    MULTIMODAL = "multimodal"  # 多模态智能体
    TOOL = "tool"           # 工具型智能体


@dataclass
class ModelConfig:
    """模型配置"""
    model_id: str                    # 模型ID (如 qwen3-max, wanx-v1, cosyvoice-v1)
    provider: str = "dashscope"      # 提供商
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    enable_thinking: bool = False
    extra_params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "enable_thinking": self.enable_thinking,
            "extra_params": self.extra_params,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfig":
        return cls(
            model_id=data["model_id"],
            provider=data.get("provider", "dashscope"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens"),
            enable_thinking=data.get("enable_thinking", False),
            extra_params=data.get("extra_params", {}),
        )


@dataclass
class RegisteredAgent:
    """注册的智能体"""
    id: str                          # 唯一ID
    name: str                        # 显示名称
    role_key: str                    # 角色键（用于匹配任务）
    description: str                 # 描述
    agent_type: AgentType            # 智能体类型
    capabilities: List[AgentCapability]  # 能力列表
    model_config: ModelConfig        # 模型配置
    system_prompt: str               # 系统提示词
    avatar: str = "🤖"               # 头像
    available_tools: List[str] = field(default_factory=list)  # 可用工具
    is_enabled: bool = True          # 是否启用
    is_builtin: bool = False         # 是否内置
    priority: int = 0                # 优先级（越高越优先被选择）
    tags: List[str] = field(default_factory=list)  # 标签
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role_key": self.role_key,
            "description": self.description,
            "agent_type": self.agent_type.value,
            "capabilities": [c.value for c in self.capabilities],
            "model_config": self.model_config.to_dict(),
            "system_prompt": self.system_prompt,
            "avatar": self.avatar,
            "available_tools": self.available_tools,
            "is_enabled": self.is_enabled,
            "is_builtin": self.is_builtin,
            "priority": self.priority,
            "tags": self.tags,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegisteredAgent":
        return cls(
            id=data["id"],
            name=data["name"],
            role_key=data["role_key"],
            description=data["description"],
            agent_type=AgentType(data["agent_type"]),
            capabilities=[AgentCapability(c) for c in data["capabilities"]],
            model_config=ModelConfig.from_dict(data["model_config"]),
            system_prompt=data["system_prompt"],
            avatar=data.get("avatar", "🤖"),
            available_tools=data.get("available_tools", []),
            is_enabled=data.get("is_enabled", True),
            is_builtin=data.get("is_builtin", False),
            priority=data.get("priority", 0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class AgentRegistry:
    """智能体注册中心"""
    
    def __init__(self, config_path: Optional[str] = None):
        self._agents: Dict[str, RegisteredAgent] = {}
        self._config_path = config_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "agents.json"
        )
        self._load_builtin_agents()
        self._load_custom_agents()
    
    def _load_builtin_agents(self):
        """加载内置智能体"""
        # 从 PREDEFINED_ROLES 导入
        from .agent import PREDEFINED_ROLES, ROLE_MODEL_CONFIG
        
        # 头像映射
        avatars = {
            "searcher": "🔍", "fact_checker": "✅", "extractor": "📤",
            "analyst": "📊", "researcher": "🔬", "strategist": "🎯", "consultant": "💼",
            "writer": "✍️", "copywriter": "📣", "creative": "💡", "editor": "📝", "summarizer": "📋",
            "coder": "💻", "debugger": "🐛", "reviewer": "🔎", "architect": "🏗️",
            "translator": "🌐", "formatter": "📐", "classifier": "🏷️",
            "document_analyst": "📄", "legal_reviewer": "⚖️", "assistant": "🤖",
            "image_analyst": "🖼️", "ocr_reader": "📖", "chart_reader": "📈", 
            "ui_analyst": "🎨", "image_describer": "🔭", "visual_qa": "❓",
        }
        
        # 能力映射
        capability_map = {
            "searcher": [AgentCapability.WEB_SEARCH, AgentCapability.TEXT_ANALYSIS],
            "analyst": [AgentCapability.TEXT_ANALYSIS, AgentCapability.TEXT_GENERATION],
            "researcher": [AgentCapability.WEB_SEARCH, AgentCapability.TEXT_ANALYSIS, AgentCapability.TEXT_GENERATION],
            "writer": [AgentCapability.TEXT_GENERATION],
            "coder": [AgentCapability.CODE_GENERATION, AgentCapability.CODE_EXECUTION],
            "translator": [AgentCapability.TEXT_TRANSLATION],
            "image_analyst": [AgentCapability.IMAGE_UNDERSTANDING],
            "ocr_reader": [AgentCapability.OCR, AgentCapability.IMAGE_UNDERSTANDING],
            "visual_qa": [AgentCapability.IMAGE_UNDERSTANDING, AgentCapability.TEXT_GENERATION],
        }
        
        for role_key, role in PREDEFINED_ROLES.items():
            model_cfg = ROLE_MODEL_CONFIG.get(role_key, {"model": "qwen3-max", "temperature": 0.5})
            
            # 确定智能体类型
            if role_key in ["image_analyst", "ocr_reader", "chart_reader", "ui_analyst", "image_describer", "visual_qa"]:
                agent_type = AgentType.VISION
            else:
                agent_type = AgentType.TEXT
            
            agent = RegisteredAgent(
                id=f"builtin_{role_key}",
                name=role.name,
                role_key=role_key,
                description=role.description,
                agent_type=agent_type,
                capabilities=capability_map.get(role_key, [AgentCapability.TEXT_GENERATION]),
                model_config=ModelConfig(
                    model_id=model_cfg.get("model", "qwen3-max"),
                    temperature=model_cfg.get("temperature", 0.5),
                    enable_thinking=model_cfg.get("enable_thinking", False),
                ),
                system_prompt=role.system_prompt,
                avatar=avatars.get(role_key, "🤖"),
                available_tools=role.available_tools,
                is_enabled=True,
                is_builtin=True,
                priority=10,
                tags=["builtin", agent_type.value],
            )
            self._agents[agent.id] = agent
    
    def _load_custom_agents(self):
        """从配置文件加载自定义智能体"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for agent_data in data.get("agents", []):
                        agent = RegisteredAgent.from_dict(agent_data)
                        self._agents[agent.id] = agent
            except Exception as e:
                print(f"加载自定义智能体失败: {e}")
    
    def _save_custom_agents(self):
        """保存自定义智能体到配置文件"""
        custom_agents = [
            agent.to_dict() for agent in self._agents.values()
            if not agent.is_builtin
        ]
        
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump({"agents": custom_agents}, f, ensure_ascii=False, indent=2)
    
    def register(self, agent: RegisteredAgent) -> bool:
        """注册新智能体（招聘）"""
        if agent.id in self._agents:
            return False
        self._agents[agent.id] = agent
        if not agent.is_builtin:
            self._save_custom_agents()
        return True
    
    def unregister(self, agent_id: str) -> bool:
        """注销智能体（解雇）"""
        if agent_id not in self._agents:
            return False
        agent = self._agents[agent_id]
        if agent.is_builtin:
            # 内置智能体只能禁用，不能删除
            agent.is_enabled = False
            return True
        del self._agents[agent_id]
        self._save_custom_agents()
        return True
    
    def enable(self, agent_id: str) -> bool:
        """启用智能体"""
        if agent_id not in self._agents:
            return False
        self._agents[agent_id].is_enabled = True
        if not self._agents[agent_id].is_builtin:
            self._save_custom_agents()
        return True
    
    def disable(self, agent_id: str) -> bool:
        """禁用智能体"""
        if agent_id not in self._agents:
            return False
        self._agents[agent_id].is_enabled = False
        if not self._agents[agent_id].is_builtin:
            self._save_custom_agents()
        return True
    
    def get(self, agent_id: str) -> Optional[RegisteredAgent]:
        """获取智能体"""
        return self._agents.get(agent_id)
    
    def get_by_role(self, role_key: str) -> Optional[RegisteredAgent]:
        """根据角色键获取智能体"""
        for agent in self._agents.values():
            if agent.role_key == role_key and agent.is_enabled:
                return agent
        return None
    
    def list_all(self, include_disabled: bool = False) -> List[RegisteredAgent]:
        """列出所有智能体"""
        agents = list(self._agents.values())
        if not include_disabled:
            agents = [a for a in agents if a.is_enabled]
        return sorted(agents, key=lambda a: (-a.priority, a.name))
    
    def list_by_type(self, agent_type: AgentType) -> List[RegisteredAgent]:
        """按类型列出智能体"""
        return [
            a for a in self._agents.values()
            if a.agent_type == agent_type and a.is_enabled
        ]
    
    def list_by_capability(self, capability: AgentCapability) -> List[RegisteredAgent]:
        """按能力列出智能体"""
        return [
            a for a in self._agents.values()
            if capability in a.capabilities and a.is_enabled
        ]
    
    def find_best_agent(
        self, 
        required_capabilities: List[AgentCapability],
        preferred_type: Optional[AgentType] = None,
    ) -> Optional[RegisteredAgent]:
        """找到最适合的智能体"""
        candidates = []
        for agent in self._agents.values():
            if not agent.is_enabled:
                continue
            # 检查是否具备所有必需能力
            if all(cap in agent.capabilities for cap in required_capabilities):
                score = agent.priority
                if preferred_type and agent.agent_type == preferred_type:
                    score += 5
                candidates.append((score, agent))
        
        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]
    
    def update(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """更新智能体配置"""
        if agent_id not in self._agents:
            return False
        
        agent = self._agents[agent_id]
        
        # 更新允许的字段
        allowed_fields = [
            "name", "description", "system_prompt", "avatar",
            "available_tools", "is_enabled", "priority", "tags", "metadata"
        ]
        
        for field in allowed_fields:
            if field in updates:
                setattr(agent, field, updates[field])
        
        # 更新模型配置
        if "model_config" in updates:
            agent.model_config = ModelConfig.from_dict(updates["model_config"])
        
        if not agent.is_builtin:
            self._save_custom_agents()
        
        return True


# ==================== 预定义多模态智能体模板 ====================

MULTIMODAL_AGENT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # ==================== 图像生成类 ====================
    
    # 文生图智能体 (通义万相 2.1)
    "text_to_image": {
        "name": "AI 文生图画师",
        "role_key": "text_to_image",
        "description": "根据文字描述生成高质量图像，使用通义万相2.1模型",
        "agent_type": AgentType.MULTIMODAL,
        "capabilities": [AgentCapability.IMAGE_GENERATION, AgentCapability.TEXT_ANALYSIS],
        "model_config": ModelConfig(
            model_id="wanx2.1-t2i-turbo",
            provider="dashscope",
            extra_params={
                "size": "1024*1024",
                "n": 1,
                "prompt_extend": True,  # 自动优化提示词
            }
        ),
        "system_prompt": """你是一个专业的AI文生图画师，使用通义万相2.1模型根据文字描述生成图像。

## 核心能力
- 根据文字描述生成高质量图像
- 支持多种风格：写实、动漫、油画、水彩、3D渲染、像素风等
- 自动优化和扩展提示词

## 工作流程
1. 理解用户的图像需求和风格偏好
2. 将中文描述翻译/优化为英文提示词（效果更好）
3. 调用 wanx2.1-t2i-turbo 模型生成图像
4. 返回生成的图像URL

## 提示词优化技巧
- 主体描述：清晰描述主要对象（如：a cute cat, a beautiful landscape）
- 风格关键词：realistic, anime style, oil painting, watercolor, 3D render
- 质量关键词：high quality, 4K, detailed, masterpiece, best quality
- 光影描述：soft lighting, golden hour, dramatic lighting, studio lighting
- 构图描述：close-up, wide shot, bird's eye view, portrait

## 输出要求
- 返回生成的图像URL
- 说明使用的提示词
- 如果生成失败，说明原因并建议调整""",
        "avatar": "🎨",
        "available_tools": [],
        "tags": ["multimodal", "creative", "wanx", "t2i", "image_generation"],
    },
    
    # ==================== 视频生成类 ====================
    
    # 文生视频智能体
    "text_to_video": {
        "name": "AI 文生视频导演",
        "role_key": "text_to_video",
        "description": "根据文字描述生成视频，使用通义万相2.1视频模型",
        "agent_type": AgentType.MULTIMODAL,
        "capabilities": [AgentCapability.VIDEO_GENERATION, AgentCapability.TEXT_ANALYSIS],
        "model_config": ModelConfig(
            model_id="wanx2.1-t2v-turbo",
            provider="dashscope",
            extra_params={
                "size": "1280*720",
                "duration": 5,  # 视频时长（秒）
                "prompt_extend": True,
            }
        ),
        "system_prompt": """你是一个专业的AI文生视频导演，使用通义万相2.1模型根据文字描述生成视频。

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
- 场景描述：清晰描述场景环境（如：in a forest, on the beach, in a city）
- 主体动作：描述主要动作（如：walking, running, flying, dancing）
- 镜头运动：camera pan, zoom in, tracking shot, static shot
- 风格关键词：cinematic, realistic, anime, slow motion
- 氛围描述：peaceful, dramatic, energetic, mysterious

## 视频参数
- 分辨率：1280*720 (720P)
- 时长：约5秒
- 格式：MP4

## 输出要求
- 返回生成的视频URL
- 说明使用的提示词
- 预估生成时间（通常1-3分钟）""",
        "avatar": "🎬",
        "available_tools": [],
        "tags": ["multimodal", "creative", "wanx", "t2v", "video_generation"],
    },
    
    # 图生视频智能体
    "image_to_video": {
        "name": "AI 图生视频动画师",
        "role_key": "image_to_video",
        "description": "将静态图片转换为动态视频，使用通义万相2.1图生视频模型",
        "agent_type": AgentType.MULTIMODAL,
        "capabilities": [AgentCapability.VIDEO_GENERATION, AgentCapability.IMAGE_UNDERSTANDING],
        "model_config": ModelConfig(
            model_id="wanx2.1-i2v-turbo",
            provider="dashscope",
            extra_params={
                "duration": 5,
                "prompt_extend": True,
            }
        ),
        "system_prompt": """你是一个专业的AI图生视频动画师，使用通义万相2.1模型将静态图片转换为动态视频。

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
- 人物动作：walking forward, turning head, waving hand, smiling
- 自然场景：wind blowing, water flowing, clouds moving, leaves falling
- 镜头效果：slow zoom in, camera pan left, parallax effect
- 氛围变化：lighting change, day to night

## 输入要求
- 图片URL（支持常见图片格式）
- 可选：动作描述（如不提供，将自动分析图片生成合适动作）

## 输出要求
- 返回生成的视频URL
- 说明应用的动态效果
- 预估生成时间（通常1-3分钟）""",
        "avatar": "🎞️",
        "available_tools": [],
        "tags": ["multimodal", "creative", "wanx", "i2v", "video_generation"],
    },
    
    # ==================== 语音类 ====================
    
    # 语音合成智能体 (CosyVoice)
    "voice_synthesizer": {
        "name": "AI 配音师",
        "role_key": "voice_synthesizer",
        "description": "使用 CosyVoice 进行高质量语音合成，支持多种音色",
        "agent_type": AgentType.AUDIO,
        "capabilities": [AgentCapability.TEXT_TO_SPEECH],
        "model_config": ModelConfig(
            model_id="cosyvoice-v1",
            provider="dashscope",
            extra_params={"voice": "longxiaochun", "format": "mp3"}
        ),
        "system_prompt": """你是一个专业的AI配音师，使用CosyVoice进行语音合成。

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
        "avatar": "🎙️",
        "available_tools": [],
        "tags": ["audio", "tts", "cosyvoice"],
    },
}


def create_agent_from_template(template_key: str, custom_id: Optional[str] = None) -> Optional[RegisteredAgent]:
    """从模板创建智能体"""
    if template_key not in MULTIMODAL_AGENT_TEMPLATES:
        return None
    
    template = MULTIMODAL_AGENT_TEMPLATES[template_key]
    agent_id = custom_id or f"custom_{template_key}_{os.urandom(4).hex()}"
    
    return RegisteredAgent(
        id=agent_id,
        name=template["name"],
        role_key=template["role_key"],
        description=template["description"],
        agent_type=template["agent_type"],
        capabilities=template["capabilities"],
        model_config=template["model_config"],
        system_prompt=template["system_prompt"],
        avatar=template.get("avatar", "🤖"),
        available_tools=template.get("available_tools", []),
        is_enabled=True,
        is_builtin=False,
        priority=5,
        tags=template.get("tags", []),
    )


# 全局注册中心实例
_registry: Optional[AgentRegistry] = None

def get_registry() -> AgentRegistry:
    """获取全局注册中心"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
