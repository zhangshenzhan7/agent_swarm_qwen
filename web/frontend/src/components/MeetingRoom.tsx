import { useEffect, useState, useMemo, useCallback } from 'react'
import type { Agent } from '../types'
import { API_BASE } from '../config'

interface MeetingRoomProps {
  agents: Agent[]
  onAgentClick: (agentId: string) => void
  agentStreams?: Record<string, string>
}

// 角色配置
const ROLE_CONFIG: Record<string, { color: string; emoji: string; title: string; gender: 'male' | 'female'; workPhrases: string[]; idlePhrases: string[] }> = {
  supervisor: { 
    color: '#a855f7', emoji: '👨‍💼', title: '主管', gender: 'male',
    workPhrases: ['🤔 分析任务中...', '📋 制定计划...', '👥 分配工作...', '📊 评估进度...'],
    idlePhrases: ['☕ 喝杯咖啡', '📱 看看消息', '🤔 思考人生']
  },
  researcher: { 
    color: '#3b82f6', emoji: '👩‍🔬', title: '研究员', gender: 'female',
    workPhrases: ['📚 查阅资料...', '🔍 深入分析...', '📝 整理数据...', '💡 有发现！'],
    idlePhrases: ['📖 看论文', '🧪 做实验', '☕ 补充咖啡因']
  },
  coder: { 
    color: '#10b981', emoji: '👨‍💻', title: '程序员', gender: 'male',
    workPhrases: ['⌨️ 敲代码中...', '🐛 调试Bug...', '🚀 优化性能...', '✅ 代码完成！'],
    idlePhrases: ['🎮 摸鱼中', '☕ 续命咖啡', '💤 眯一会']
  },
  analyst: { 
    color: '#f59e0b', emoji: '👩‍💼', title: '分析师', gender: 'female',
    workPhrases: ['📈 分析数据...', '📉 生成图表...', '🎯 预测趋势...', '✨ 分析完成！'],
    idlePhrases: ['📱 刷手机', '🍪 吃零食', '💬 闲聊中']
  },
  writer: { 
    color: '#ec4899', emoji: '👩‍🎨', title: '文案', gender: 'female',
    workPhrases: ['💭 构思中...', '✏️ 撰写文案...', '📝 润色文字...', '🎨 排版设计...'],
    idlePhrases: ['📚 找灵感', '☕ 喝奶茶', '🎧 听音乐']
  },
  searcher: { 
    color: '#8b5cf6', emoji: '👨‍🔍', title: '搜索员', gender: 'male',
    workPhrases: ['🌐 搜索中...', '📋 筛选结果...', '✅ 验证信息...', '📊 汇总发现...'],
    idlePhrases: ['🎮 玩游戏', '📱 刷视频', '💤 打盹中']
  },
  summarizer: { 
    color: '#f97316', emoji: '👩‍📝', title: '总结员', gender: 'female',
    workPhrases: ['📄 整理内容...', '✨ 提炼要点...', '📋 生成报告...', '✅ 审核通过！'],
    idlePhrases: ['☕ 休息一下', '📖 看书中', '🎧 听播客']
  },
  document_analyst: {
    color: '#14b8a6', emoji: '👨‍📊', title: '文档分析', gender: 'male',
    workPhrases: ['📖 阅读文档...', '🔍 提取信息...', '📊 分析结构...', '📝 生成摘要...'],
    idlePhrases: ['📚 整理文件', '☕ 喝茶中', '💭 发呆中']
  },
  quality_checker: {
    color: '#f43f5e', emoji: '🔬', title: '质量检查', gender: 'female',
    workPhrases: ['🔍 审查报告...', '📊 评估质量...', '✅ 检测冲突...', '🔄 反思改进...'],
    idlePhrases: ['📋 整理标准', '☕ 喝茶中', '💭 思考质量']
  },
  default: { 
    color: '#6b7280', emoji: '👤', title: '员工', gender: 'male',
    workPhrases: ['⚙️ 处理中...', '🔧 执行任务...', '📋 工作中...', '✅ 完成！'],
    idlePhrases: ['☕ 休息中', '📱 看手机', '💤 打盹']
  },
}

// 座位位置
const SEAT_POSITIONS = [
  { x: 0, y: -110, rotation: 0 },
  { x: -90, y: -55, rotation: 35 },
  { x: 90, y: -55, rotation: -35 },
  { x: -105, y: 25, rotation: 65 },
  { x: 105, y: 25, rotation: -65 },
  { x: -70, y: 90, rotation: 115 },
  { x: 70, y: 90, rotation: -115 },
  { x: 0, y: 110, rotation: 180 },
]

// 办公室事件类型
type OfficeEvent = {
  id: string
  type: 'romance' | 'activity' | 'gossip' | 'celebration' | 'coffee' | 'meeting' | 'birthday'
  participants: string[]
  message: string
  emoji: string
  duration: number
}

// 办公室八卦/事件消息
const OFFICE_GOSSIPS = [
  { emoji: '💕', message: '听说研究员和程序员在茶水间聊了很久...' },
  { emoji: '🎂', message: '今天是文案小姐姐的生日！' },
  { emoji: '🏆', message: '分析师上个月业绩第一！' },
  { emoji: '🌸', message: '办公室的绿植开花了~' },
  { emoji: '🍕', message: '主管请大家吃披萨！' },
  { emoji: '😴', message: '有人在会议室睡着了...' },
  { emoji: '🎵', message: '谁在放音乐？好好听！' },
  { emoji: '☕', message: '咖啡机又坏了...' },
  { emoji: '🐱', message: '有人偷偷带猫来上班！' },
  { emoji: '🎮', message: '午休时间王者荣耀开黑！' },
]

// 集体活动
const GROUP_ACTIVITIES = [
  { emoji: '🧘', name: '午间瑜伽', message: '大家一起做瑜伽放松~' },
  { emoji: '🎤', name: 'K歌时间', message: '谁来唱一首？' },
  { emoji: '🏃', name: '工间操', message: '站起来活动活动！' },
  { emoji: '🎲', name: '桌游时间', message: '来一局狼人杀？' },
  { emoji: '📸', name: '团建合影', message: '茄子！📷' },
  { emoji: '🍰', name: '下午茶', message: '今天的蛋糕超好吃！' },
]

// 办公室恋情配对（基于角色）
const ROMANCE_PAIRS = [
  { role1: 'coder', role2: 'writer', story: '程序员默默帮文案修好了电脑...' },
  { role1: 'researcher', role2: 'analyst', story: '研究员和分析师一起加班到深夜...' },
  { role1: 'searcher', role2: 'summarizer', story: '搜索员给总结员带了早餐~' },
]

// 表情反应
const REACTIONS = ['👍', '❤️', '😂', '🎉', '👏', '🔥', '💯', '✨']

// 天气/时间氛围
const AMBIANCES = [
  { time: '早晨', emoji: '🌅', mood: '元气满满的一天开始了！' },
  { time: '上午', emoji: '☀️', mood: '阳光正好，努力工作！' },
  { time: '中午', emoji: '🍱', mood: '午餐时间到~' },
  { time: '下午', emoji: '☕', mood: '下午茶时间，补充能量！' },
  { time: '傍晚', emoji: '🌆', mood: '快下班了，再坚持一下！' },
  { time: '加班', emoji: '🌙', mood: '夜深了，辛苦了...' },
]

// AI 生成的剧情数据类型
interface GeneratedStory {
  gossips: { emoji: string; message: string }[]
  activities: { emoji: string; name: string; message: string }[]
  romances: { role1: string; role2: string; story: string }[]
  workPhrases: Record<string, string[]>
  idlePhrases: Record<string, string[]>
}

export function MeetingRoom({ agents, onAgentClick }: MeetingRoomProps) {
  const [time, setTime] = useState(0)
  const [bubbles, setBubbles] = useState<Record<string, string>>({})
  const [currentEvent, setCurrentEvent] = useState<OfficeEvent | null>(null)
  const [gossip, setGossip] = useState(OFFICE_GOSSIPS[0])
  const [ambiance, setAmbiance] = useState(AMBIANCES[0])
  const [showHearts, setShowHearts] = useState<{x: number, y: number}[]>([])
  const [reactions, setReactions] = useState<{id: string, emoji: string, x: number, y: number}[]>([])
  const [isPartyMode, setIsPartyMode] = useState(false)
  const [coffeeCount, setCoffeeCount] = useState(0)
  
  // AI 生成剧情相关状态
  const [generatedStory, setGeneratedStory] = useState<GeneratedStory | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [storyGenCount, setStoryGenCount] = useState(0)
  
  // 合并默认剧情和 AI 生成的剧情
  const currentGossips = useMemo(() => {
    if (generatedStory?.gossips?.length) {
      return [...OFFICE_GOSSIPS, ...generatedStory.gossips]
    }
    return OFFICE_GOSSIPS
  }, [generatedStory])
  
  const currentActivities = useMemo(() => {
    if (generatedStory?.activities?.length) {
      return [...GROUP_ACTIVITIES, ...generatedStory.activities]
    }
    return GROUP_ACTIVITIES
  }, [generatedStory])
  
  const currentRomances = useMemo(() => {
    if (generatedStory?.romances?.length) {
      return [...ROMANCE_PAIRS, ...generatedStory.romances]
    }
    return ROMANCE_PAIRS
  }, [generatedStory])
  
  // 获取角色的状态语（合并默认和 AI 生成的）
  const getRolePhrases = useCallback((role: string, isWorking: boolean) => {
    const config = ROLE_CONFIG[role] || ROLE_CONFIG.default
    const defaultPhrases = isWorking ? config.workPhrases : config.idlePhrases
    
    if (generatedStory) {
      const genPhrases = isWorking 
        ? generatedStory.workPhrases?.[role] 
        : generatedStory.idlePhrases?.[role]
      if (genPhrases?.length) {
        return [...defaultPhrases, ...genPhrases]
      }
    }
    return defaultPhrases
  }, [generatedStory])
  
  // 动画时钟
  useEffect(() => {
    const interval = setInterval(() => setTime(t => t + 1), 50)
    return () => clearInterval(interval)
  }, [])

  // 分类员工
  const { supervisor, workingAgents, idleAgents } = useMemo(() => {
    // 优先选择 running 状态的 supervisor 实例，否则用模板
    const allSups = agents.filter(a => a.role === 'supervisor')
    const sup = allSups.find(a => a.status === 'running') || allSups[0]
    const supId = sup?.id
    const working = agents.filter(a => a.status === 'running' && a.id !== supId && a.role !== 'supervisor')
    const idle = agents.filter(a => a.status !== 'running' && a.id !== supId && a.role !== 'supervisor')
    return { supervisor: sup, workingAgents: working, idleAgents: idle }
  }, [agents])

  // 八卦轮换（使用合并后的数据）
  useEffect(() => {
    const interval = setInterval(() => {
      setGossip(currentGossips[Math.floor(Math.random() * currentGossips.length)])
    }, 8000)
    return () => clearInterval(interval)
  }, [currentGossips])

  // 氛围轮换
  useEffect(() => {
    const interval = setInterval(() => {
      setAmbiance(AMBIANCES[Math.floor(Math.random() * AMBIANCES.length)])
    }, 15000)
    return () => clearInterval(interval)
  }, [])

  // 随机办公室事件（使用合并后的数据）
  useEffect(() => {
    if (workingAgents.length > 0) return // 工作时不触发娱乐事件
    
    const interval = setInterval(() => {
      const rand = Math.random()
      if (rand < 0.1 && currentRomances.length > 0) {
        // 触发恋情事件
        const pair = currentRomances[Math.floor(Math.random() * currentRomances.length)]
        triggerRomanceEvent(pair)
      } else if (rand < 0.2 && currentActivities.length > 0) {
        // 触发集体活动
        const activity = currentActivities[Math.floor(Math.random() * currentActivities.length)]
        triggerActivityEvent(activity)
      }
    }, 12000)
    return () => clearInterval(interval)
  }, [workingAgents.length, currentRomances, currentActivities])

  // 触发恋情事件
  const triggerRomanceEvent = useCallback((pair: typeof ROMANCE_PAIRS[0]) => {
    setCurrentEvent({
      id: Date.now().toString(),
      type: 'romance',
      participants: [pair.role1, pair.role2],
      message: pair.story,
      emoji: '💕',
      duration: 5000
    })
    // 显示爱心
    const hearts = Array.from({length: 8}, () => ({
      x: 40 + Math.random() * 20,
      y: 30 + Math.random() * 40
    }))
    setShowHearts(hearts)
    setTimeout(() => {
      setShowHearts([])
      setCurrentEvent(null)
    }, 5000)
  }, [])

  // 触发集体活动
  const triggerActivityEvent = useCallback((activity: typeof GROUP_ACTIVITIES[0]) => {
    setCurrentEvent({
      id: Date.now().toString(),
      type: 'activity',
      participants: [],
      message: activity.message,
      emoji: activity.emoji,
      duration: 4000
    })
    setTimeout(() => setCurrentEvent(null), 4000)
  }, [])

  // 添加反应表情
  const addReaction = useCallback((emoji: string) => {
    const newReaction = {
      id: Date.now().toString(),
      emoji,
      x: 20 + Math.random() * 60,
      y: 70 + Math.random() * 20
    }
    setReactions(prev => [...prev, newReaction])
    setTimeout(() => {
      setReactions(prev => prev.filter(r => r.id !== newReaction.id))
    }, 2000)
  }, [])

  // 自动生成新剧情（每10秒）
  const generateNewStory = useCallback(async () => {
    if (isGenerating) return
    setIsGenerating(true)
    
    try {
      const res = await fetch(`${API_BASE}/api/meeting/generate-story`, {
        method: 'POST',
        credentials: 'include'
      })
      const data = await res.json()
      
      if (data.success && data.data) {
        setGeneratedStory(data.data)
        setStoryGenCount(prev => prev + 1)
      }
    } catch (err) {
      console.error('生成剧情失败:', err)
    } finally {
      setIsGenerating(false)
    }
  }, [isGenerating])

  // 每10秒自动生成新剧情
  useEffect(() => {
    // 首次加载时生成
    generateNewStory()
    
    // 每10秒生成一次
    const interval = setInterval(() => {
      generateNewStory()
    }, 10000)
    
    return () => clearInterval(interval)
  }, []) // 只在组件挂载时启动

  // 派对模式
  const togglePartyMode = useCallback(() => {
    setIsPartyMode(prev => !prev)
    if (!isPartyMode) {
      // 触发庆祝
      for (let i = 0; i < 5; i++) {
        setTimeout(() => addReaction('🎉'), i * 200)
      }
    }
  }, [isPartyMode, addReaction])

  // 喝咖啡
  const drinkCoffee = useCallback(() => {
    setCoffeeCount(prev => prev + 1)
    addReaction('☕')
  }, [addReaction])

  // 生成对话气泡（使用合并后的状态语）
  useEffect(() => {
    const allAgents = agents.filter(a => a.role !== 'supervisor')
    if (allAgents.length === 0) return

    const interval = setInterval(() => {
      const agent = allAgents[Math.floor(Math.random() * allAgents.length)]
      const isWorking = agent.status === 'running'
      const phrases = getRolePhrases(agent.role || 'default', isWorking)
      const phrase = phrases[Math.floor(Math.random() * phrases.length)]

      setBubbles(prev => ({ ...prev, [agent.id]: phrase }))
      setTimeout(() => {
        setBubbles(prev => {
          const next = { ...prev }
          delete next[agent.id]
          return next
        })
      }, 3500)
    }, 2500)

    return () => clearInterval(interval)
  }, [agents, getRolePhrases])

  const displayAgents = [...workingAgents, ...idleAgents].slice(0, 7)
  const workingCount = workingAgents.length
  const totalCount = agents.length

  return (
    <div className={`relative w-full h-full overflow-hidden transition-all duration-1000 ${
      isPartyMode 
        ? 'bg-gradient-to-b from-purple-900/50 via-pink-900/30 to-[#0d1220]' 
        : 'bg-gradient-to-b from-[#080c14] via-[#0a0e17] to-[#0d1220]'
    }`}>
      {/* CSS 动画 */}
      <style>{`
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        @keyframes float-heart { 0% { opacity: 1; transform: translateY(0) scale(1); } 100% { opacity: 0; transform: translateY(-50px) scale(1.5); } }
        @keyframes pulse-ring { 0% { transform: scale(0.8); opacity: 0.8; } 50% { transform: scale(1.2); opacity: 0.3; } 100% { transform: scale(0.8); opacity: 0.8; } }
        @keyframes confetti { 0% { transform: translateY(0) rotate(0deg); opacity: 1; } 100% { transform: translateY(100vh) rotate(720deg); opacity: 0; } }
        @keyframes disco { 0%, 100% { filter: hue-rotate(0deg); } 50% { filter: hue-rotate(180deg); } }
        @keyframes bounce-in { 0% { transform: scale(0); } 50% { transform: scale(1.2); } 100% { transform: scale(1); } }
        @keyframes wiggle { 0%, 100% { transform: rotate(-3deg); } 50% { transform: rotate(3deg); } }
      `}</style>

      {/* 派对模式彩带 */}
      {isPartyMode && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden z-50">
          {Array.from({ length: 30 }).map((_, i) => (
            <div
              key={i}
              className="absolute w-3 h-3 rounded-sm"
              style={{
                left: `${Math.random() * 100}%`,
                top: '-20px',
                backgroundColor: ['#a855f7', '#3b82f6', '#10b981', '#f59e0b', '#ec4899'][i % 5],
                animation: `confetti ${3 + Math.random() * 2}s linear infinite`,
                animationDelay: `${Math.random() * 2}s`,
              }}
            />
          ))}
        </div>
      )}

      {/* 飘浮的爱心 */}
      {showHearts.map((heart, i) => (
        <div
          key={i}
          className="absolute text-2xl pointer-events-none z-40"
          style={{
            left: `${heart.x}%`,
            top: `${heart.y}%`,
            animation: 'float-heart 2s ease-out forwards',
            animationDelay: `${i * 0.1}s`
          }}
        >
          💕
        </div>
      ))}

      {/* 反应表情 */}
      {reactions.map(r => (
        <div
          key={r.id}
          className="absolute text-3xl pointer-events-none z-40"
          style={{
            left: `${r.x}%`,
            top: `${r.y}%`,
            animation: 'float-heart 2s ease-out forwards'
          }}
        >
          {r.emoji}
        </div>
      ))}

      {/* 顶部信息栏 */}
      <div className="absolute top-4 left-4 right-4 flex items-start justify-between z-20">
        {/* 左侧：标题和氛围 */}
        <div>
          <h2 className={`text-2xl font-bold bg-clip-text text-transparent ${
            isPartyMode 
              ? 'bg-gradient-to-r from-pink-400 via-purple-400 to-cyan-400 animate-pulse' 
              : 'bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400'
          }`}>
            🏢 AI 协作会议室
          </h2>
          {/* 氛围提示 */}
          <div className="mt-2 flex items-center gap-2 text-sm">
            <span className="text-xl">{ambiance.emoji}</span>
            <span className="text-slate-400">{ambiance.time} · {ambiance.mood}</span>
          </div>
        </div>

        {/* 右侧：八卦栏 */}
        <div className="max-w-xs">
          <div className="px-4 py-2 rounded-xl bg-pink-500/10 border border-pink-500/30 backdrop-blur-sm">
            <p className="text-xs text-pink-300 flex items-center gap-2">
              <span className="text-lg">{gossip.emoji}</span>
              <span className="italic">"{gossip.message}"</span>
            </p>
          </div>
        </div>
      </div>

      {/* 当前事件提示 */}
      {currentEvent && (
        <div 
          className="absolute top-24 left-1/2 -translate-x-1/2 z-30 px-6 py-3 rounded-2xl bg-gradient-to-r from-pink-500/20 to-purple-500/20 border border-pink-400/50 backdrop-blur-md shadow-xl"
          style={{ animation: 'bounce-in 0.5s ease-out' }}
        >
          <p className="text-lg text-white flex items-center gap-3">
            <span className="text-2xl" style={{ animation: 'wiggle 0.5s ease-in-out infinite' }}>{currentEvent.emoji}</span>
            <span>{currentEvent.message}</span>
          </p>
        </div>
      )}

      {/* 会议桌区域 */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
        <MeetingTable isActive={workingCount > 0} time={time} isPartyMode={isPartyMode} />

        {supervisor && (
          <AgentAvatar
            agent={supervisor}
            position={SEAT_POSITIONS[0]}
            bubble={bubbles[supervisor.id]}
            time={time}
            onClick={() => onAgentClick(supervisor.id)}
            isMain
            isPartyMode={isPartyMode}
            isInRomance={currentEvent?.type === 'romance' && currentEvent.participants.includes(supervisor.role || '')}
          />
        )}

        {displayAgents.map((agent, i) => (
          <AgentAvatar
            key={agent.id}
            agent={agent}
            position={SEAT_POSITIONS[i + 1]}
            bubble={bubbles[agent.id]}
            time={time}
            onClick={() => onAgentClick(agent.id)}
            isPartyMode={isPartyMode}
            isInRomance={currentEvent?.type === 'romance' && currentEvent.participants.includes(agent.role || '')}
          />
        ))}
      </div>

      {/* 右侧状态面板 */}
      <WorkStatusPanel 
        workingAgents={workingAgents} 
        idleAgents={idleAgents}
        onAgentClick={onAgentClick}
      />

      {/* 底部互动栏 */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-4 z-20">
        {/* 状态统计 */}
        <div className="flex items-center gap-6 px-6 py-3 rounded-2xl bg-slate-900/90 border border-slate-700/50 backdrop-blur-md">
          <StatusItem icon="👥" label="总人数" value={totalCount} color="cyan" />
          <div className="w-px h-8 bg-slate-700" />
          <StatusItem icon="⚡" label="工作中" value={workingCount} color="emerald" pulse={workingCount > 0} />
          <div className="w-px h-8 bg-slate-700" />
          <StatusItem icon="☕" label="咖啡" value={coffeeCount} color="amber" />
        </div>

        {/* 互动按钮 */}
        <div className="flex items-center gap-2 px-4 py-2 rounded-2xl bg-slate-900/90 border border-slate-700/50 backdrop-blur-md">
          {/* 表情反应 */}
          {REACTIONS.slice(0, 4).map(emoji => (
            <button
              key={emoji}
              onClick={() => addReaction(emoji)}
              className="w-10 h-10 rounded-xl hover:bg-slate-700/50 flex items-center justify-center text-xl transition-all hover:scale-110 active:scale-95"
            >
              {emoji}
            </button>
          ))}
          <div className="w-px h-8 bg-slate-700 mx-1" />
          {/* 喝咖啡 */}
          <button
            onClick={drinkCoffee}
            className="px-3 py-2 rounded-xl bg-amber-500/20 border border-amber-500/40 text-amber-300 text-sm hover:bg-amber-500/30 transition-all flex items-center gap-1"
          >
            ☕ 喝咖啡
          </button>
          {/* 派对模式 */}
          <button
            onClick={togglePartyMode}
            className={`px-3 py-2 rounded-xl text-sm transition-all flex items-center gap-1 ${
              isPartyMode 
                ? 'bg-gradient-to-r from-pink-500/40 to-purple-500/40 border border-pink-400/50 text-pink-200' 
                : 'bg-purple-500/20 border border-purple-500/40 text-purple-300 hover:bg-purple-500/30'
            }`}
          >
            🎉 {isPartyMode ? '停止派对' : '开派对'}
          </button>
        </div>
      </div>

      {/* 左下角趣味统计 */}
      <div className="absolute bottom-4 left-4 px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 backdrop-blur-sm">
        <p className="text-xs text-slate-500 mb-1">📊 办公室趣闻</p>
        <div className="space-y-1 text-xs">
          <p className="text-cyan-400">☕ 今日咖啡消耗: {coffeeCount} 杯</p>
          <p className="text-pink-400">💕 办公室CP: {currentRomances.length} 对</p>
          <p className="text-purple-400">🎉 团建活动: {currentActivities.length} 种</p>
          <p className="text-amber-400">📰 八卦数量: {currentGossips.length} 条</p>
          {storyGenCount > 0 && (
            <p className="text-emerald-400">✨ AI创作: {storyGenCount} 次</p>
          )}
        </div>
      </div>
    </div>
  )
}

// 状态项组件
function StatusItem({ icon, label, value, color, pulse = false }: {
  icon: string; label: string; value: string | number; color: 'cyan' | 'emerald' | 'amber' | 'purple'; pulse?: boolean
}) {
  const colorMap = { cyan: 'text-cyan-400', emerald: 'text-emerald-400', amber: 'text-amber-400', purple: 'text-purple-400' }
  return (
    <div className="flex items-center gap-2">
      <span className={`text-lg ${pulse ? 'animate-pulse' : ''}`}>{icon}</span>
      <div>
        <p className="text-[10px] text-slate-500">{label}</p>
        <p className={`text-base font-bold ${colorMap[color]}`}>{value}</p>
      </div>
    </div>
  )
}

// 会议桌组件
function MeetingTable({ isActive, time, isPartyMode }: { isActive: boolean; time: number; isPartyMode: boolean }) {
  return (
    <div className="relative">
      <div className={`absolute -top-10 left-1/2 -translate-x-1/2 px-5 py-1.5 rounded-full border backdrop-blur-sm transition-all ${
        isPartyMode ? 'bg-pink-500/30 border-pink-400/60 animate-pulse' :
        isActive ? 'bg-emerald-500/20 border-emerald-500/50' : 'bg-purple-500/20 border-purple-500/40'
      }`}>
        <span className={`text-sm font-medium ${isPartyMode ? 'text-pink-200' : isActive ? 'text-emerald-300' : 'text-purple-300'}`}>
          {isPartyMode ? '🎉 派对时间！' : isActive ? '🔥 协作中' : '☕ 休息中'}
        </span>
      </div>

      <div className="absolute top-8 left-1/2 w-[280px] h-[180px] bg-black/50 rounded-[50%] blur-2xl" style={{ transform: 'translateX(-50%) scaleY(0.25)' }} />
      
      <div 
        className={`relative w-[240px] h-[150px] rounded-[50%] border-2 transition-all duration-500 ${isPartyMode ? 'animate-pulse' : ''}`}
        style={{
          borderColor: isPartyMode ? 'rgba(236, 72, 153, 0.7)' : isActive ? 'rgba(168, 85, 247, 0.6)' : 'rgba(168, 85, 247, 0.25)',
          background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.98) 0%, rgba(30, 41, 59, 0.98) 100%)',
          boxShadow: isPartyMode 
            ? '0 0 60px rgba(236, 72, 153, 0.5), inset 0 0 40px rgba(236, 72, 153, 0.2)'
            : isActive ? '0 0 60px rgba(168, 85, 247, 0.4)' : '0 0 25px rgba(168, 85, 247, 0.15)',
          animation: isPartyMode ? 'disco 2s ease-in-out infinite' : undefined,
        }}
      >
        <div className="absolute inset-5 rounded-[50%] border border-purple-500/25" />
        
        {isActive ? (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="w-16 h-16 rounded-full border-2 border-purple-400/70" style={{ transform: `rotate(${-time * 2}deg)` }}>
              {[0, 72, 144, 216, 288].map(deg => (
                <div key={deg} className="absolute w-2.5 h-2.5 rounded-full bg-purple-400"
                  style={{ top: '50%', left: '50%', transform: `rotate(${deg}deg) translateX(28px) translateY(-50%)` }} />
              ))}
            </div>
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-gradient-to-br from-purple-400 to-pink-500"
              style={{ opacity: 0.7 + Math.sin(time * 0.08) * 0.3 }} />
          </div>
        ) : isPartyMode ? (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
            <span className="text-4xl" style={{ animation: 'wiggle 0.5s ease-in-out infinite' }}>🪩</span>
            <p className="text-xs text-pink-300 mt-2">Let's Party!</p>
          </div>
        ) : (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
            <span className="text-4xl" style={{ animation: 'float 2s ease-in-out infinite' }}>😴</span>
            <p className="text-xs text-slate-500 mt-2">休息时间</p>
          </div>
        )}
      </div>
    </div>
  )
}

// 员工头像组件
function AgentAvatar({ agent, position, bubble, time, onClick, isMain = false, isPartyMode = false, isInRomance = false }: {
  agent: Agent; position: { x: number; y: number; rotation: number }; bubble?: string; time: number
  onClick: () => void; isMain?: boolean; isPartyMode?: boolean; isInRomance?: boolean
}) {
  const isWorking = agent.status === 'running'
  const config = ROLE_CONFIG[agent.role || 'default'] || ROLE_CONFIG.default
  const breathOffset = isWorking ? Math.sin(time * 0.08) * 5 : Math.sin(time * 0.03) * 2
  const sizeNum = isMain ? 72 : 60
  const textSize = isMain ? 'text-3xl' : 'text-2xl'

  return (
    <div
      className="absolute cursor-pointer transition-all duration-300 hover:scale-110 hover:z-40 group"
      style={{
        left: `calc(50% + ${position.x}px)`,
        top: `calc(50% + ${position.y + breathOffset}px)`,
        transform: 'translate(-50%, -50%)',
        zIndex: isMain ? 25 : 15,
        animation: isPartyMode ? 'wiggle 0.5s ease-in-out infinite' : undefined,
      }}
      onClick={onClick}
    >
      {/* 恋情光环 */}
      {isInRomance && (
        <div className="absolute -inset-4 rounded-full bg-pink-500/30 animate-pulse" />
      )}

      {/* 对话气泡 */}
      {bubble && (
        <div className={`absolute -top-14 left-1/2 -translate-x-1/2 px-4 py-2 rounded-2xl z-50 whitespace-nowrap shadow-lg backdrop-blur-sm ${
          isWorking ? 'bg-cyan-500/30 border border-cyan-400/50' : 'bg-amber-500/30 border border-amber-400/50'
        }`}>
          <p className={`text-xs font-medium ${isWorking ? 'text-cyan-100' : 'text-amber-100'}`}>{bubble}</p>
          <div className={`absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-4 rotate-45 ${
            isWorking ? 'bg-cyan-500/30 border-r border-b border-cyan-400/50' : 'bg-amber-500/30 border-r border-b border-amber-400/50'
          }`} />
        </div>
      )}

      <div className="relative">
        {isWorking && (
          <>
            <div className="absolute rounded-full" style={{ inset: '-12px', background: `radial-gradient(circle, ${config.color}50 0%, transparent 70%)`, animation: 'pulse-ring 2s ease-in-out infinite' }} />
            <svg className="absolute" style={{ inset: '-8px', width: `${sizeNum + 16}px`, height: `${sizeNum + 16}px` }}>
              <circle cx="50%" cy="50%" r="45%" fill="none" stroke={config.color} strokeWidth="2" strokeDasharray="10 5" opacity="0.8"
                style={{ transform: `rotate(${time * 2}deg)`, transformOrigin: 'center' }} />
            </svg>
          </>
        )}

        <div className="relative rounded-full flex items-center justify-center transition-all shadow-xl"
          style={{
            width: sizeNum, height: sizeNum,
            backgroundColor: `${config.color}30`,
            borderWidth: '3px', borderStyle: 'solid',
            borderColor: isInRomance ? '#ec4899' : isWorking ? config.color : `${config.color}60`,
            boxShadow: isInRomance ? '0 0 30px rgba(236, 72, 153, 0.7)' : isWorking ? `0 0 30px ${config.color}70` : `0 0 15px ${config.color}40`,
          }}
        >
          <span className={textSize}>{config.emoji}</span>
          
          {/* 恋情爱心 */}
          {isInRomance && (
            <div className="absolute -top-2 -right-2 text-lg animate-bounce">💕</div>
          )}
          
          <div className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full border-2 border-slate-900 flex items-center justify-center shadow-lg ${
            isWorking ? 'bg-emerald-500' : 'bg-slate-500'
          }`}>
            <span className="text-xs">{isWorking ? '⚡' : '💤'}</span>
          </div>
        </div>

        <div className="absolute -bottom-10 left-1/2 -translate-x-1/2 text-center whitespace-nowrap">
          <p className={`text-xs font-bold ${isWorking ? 'text-white' : 'text-slate-400'}`}>
            {agent.name.replace(/^AI\s*/, '')}
          </p>
          <p className={`text-[10px] mt-0.5 ${isInRomance ? 'text-pink-400' : isWorking ? 'text-emerald-400' : 'text-slate-500'}`}>
            {isInRomance ? '💕 恋爱中' : isWorking ? '🔥 工作中' : '☕ 休息中'}
          </p>
        </div>
      </div>
    </div>
  )
}

// 右侧工作状态面板
function WorkStatusPanel({ workingAgents, idleAgents, onAgentClick }: {
  workingAgents: Agent[]; idleAgents: Agent[]; onAgentClick: (id: string) => void
}) {
  return (
    <div className="absolute right-4 top-24 bottom-24 w-72 flex flex-col gap-4 overflow-hidden">
      {workingAgents.length > 0 && (
        <div className="bg-slate-900/90 border border-emerald-500/40 rounded-2xl p-4 backdrop-blur-md shadow-xl">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
              <span className="text-lg animate-pulse">⚡</span>
            </div>
            <span className="text-sm font-bold text-emerald-400">工作中 ({workingAgents.length})</span>
          </div>
          <div className="space-y-2 max-h-[200px] overflow-auto">
            {workingAgents.map(agent => (
              <AgentStatusCard key={agent.id} agent={agent} onClick={() => onAgentClick(agent.id)} />
            ))}
          </div>
        </div>
      )}

      {idleAgents.length > 0 && (
        <div className="bg-slate-900/90 border border-slate-600/40 rounded-2xl p-4 backdrop-blur-md flex-1 overflow-hidden shadow-xl">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-slate-700/50 flex items-center justify-center">
              <span className="text-lg">☕</span>
            </div>
            <span className="text-sm font-bold text-slate-400">休息中 ({idleAgents.length})</span>
          </div>
          <div className="space-y-2 max-h-full overflow-auto">
            {idleAgents.slice(0, 8).map(agent => (
              <AgentStatusCard key={agent.id} agent={agent} onClick={() => onAgentClick(agent.id)} isIdle />
            ))}
            {idleAgents.length > 8 && (
              <p className="text-xs text-slate-500 text-center py-1">还有 {idleAgents.length - 8} 人...</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// 员工状态卡片
function AgentStatusCard({ agent, onClick, isIdle = false }: { agent: Agent; onClick: () => void; isIdle?: boolean }) {
  const config = ROLE_CONFIG[agent.role || 'default'] || ROLE_CONFIG.default
  const stableIndex = useMemo(() => {
    let hash = 0
    for (let i = 0; i < agent.id.length; i++) { hash = ((hash << 5) - hash) + agent.id.charCodeAt(i); hash |= 0 }
    return Math.abs(hash) % config.idlePhrases.length
  }, [agent.id, config.idlePhrases.length])

  return (
    <div className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all hover:scale-[1.02] ${
      isIdle ? 'bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/50' 
             : 'bg-emerald-500/15 border border-emerald-500/40 hover:bg-emerald-500/25'
    }`} onClick={onClick}>
      <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl border-2"
        style={{ backgroundColor: `${config.color}25`, borderColor: isIdle ? `${config.color}40` : config.color }}>
        {config.emoji}
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium truncate ${isIdle ? 'text-slate-300' : 'text-white'}`}>
          {agent.name.replace(/^AI\s*/, '')}
        </p>
        {agent.current_task ? (
          <p className="text-[11px] text-emerald-400 truncate">📋 {agent.current_task}</p>
        ) : (
          <p className="text-[11px] text-slate-500 truncate">{config.idlePhrases[stableIndex]}</p>
        )}
      </div>
      <div className={`w-3 h-3 rounded-full ${isIdle ? 'bg-slate-500' : 'bg-emerald-500 animate-pulse'}`} />
    </div>
  )
}
