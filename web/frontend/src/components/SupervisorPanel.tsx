import { useState, useEffect, useMemo } from 'react'
import type { Agent, Task } from '../types'

interface SupervisorPanelProps {
  supervisor: Agent | null
  currentTask: Task | null
  agentLogs: Record<string, Array<{ timestamp: string; message: string; level: string }>>
  agentStreams: Record<string, string>
  allAgents: Agent[]
  onClose?: () => void
  onClearData?: () => void  // 清除思考和日志数据的回调
}

// 清理 THINKING 标签的工具函数
function cleanThinkingTags(text: string): string {
  if (!text) return ''
  let result = text
  // 循环移除 [THINKING]...[/THINKING] 块
  for (let i = 0; i < 20; i++) {
    const newResult = result.replace(/\[THINKING\][\s\S]*?\[\/THINKING\]/gi, '')
    if (newResult === result) break
    result = newResult
  }
  // 移除单独的标签
  result = result.replace(/\[THINKING\]/gi, '')
  result = result.replace(/\[\/THINKING\]/gi, '')
  result = result.replace(/\[NEW_PHASE\]/gi, '')
  // 清理多余空行
  result = result.replace(/\n{3,}/g, '\n\n')
  return result.trim()
}

// 主管思考动画
const THINKING_ANIMATIONS = [
  '🤔 分析任务需求...',
  '📊 评估复杂度...',
  '🔍 调研背景信息...',
  '📝 制定执行计划...',
  '👥 分配团队成员...',
  '⚡ 协调任务执行...',
  '💡 灵感涌现中...',
  '🎯 锁定目标...',
  '🧩 拆解问题...',
  '📋 整理思路...',
]

// 主管心情/状态
const SUPERVISOR_MOODS = {
  working: ['😤 认真工作中', '🧐 深度思考', '💪 全力以赴', '🔥 状态火热'],
  idle: ['😌 悠闲待命', '☕ 享受咖啡', '🌟 精神饱满', '😊 心情不错'],
}

// 趣味提示语
const FUN_TIPS = [
  '💡 主管正在运筹帷幄...',
  '🎯 精准分析每个细节',
  '🧠 大脑高速运转中',
  '📊 数据分析进行时',
  '✨ 创意灵感迸发',
]

export function SupervisorPanel({ 
  supervisor, 
  currentTask, 
  agentLogs, 
  agentStreams,
  allAgents,
  onClose,
  onClearData
}: SupervisorPanelProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'plan' | 'team' | 'logs' | 'thinking'>('overview')
  const [thinkingIndex, setThinkingIndex] = useState(0)
  const [moodIndex, setMoodIndex] = useState(0)
  const [tipIndex, setTipIndex] = useState(0)
  
  const isWorking = supervisor?.status === 'running'
  
  // 思考动画
  useEffect(() => {
    if (!isWorking) return
    const interval = setInterval(() => {
      setThinkingIndex(i => (i + 1) % THINKING_ANIMATIONS.length)
    }, 2000)
    return () => clearInterval(interval)
  }, [isWorking])

  // 心情切换
  useEffect(() => {
    const interval = setInterval(() => {
      const moods = isWorking ? SUPERVISOR_MOODS.working : SUPERVISOR_MOODS.idle
      setMoodIndex(i => (i + 1) % moods.length)
    }, 4000)
    return () => clearInterval(interval)
  }, [isWorking])

  // 趣味提示
  useEffect(() => {
    if (!isWorking) return
    const interval = setInterval(() => {
      setTipIndex(i => (i + 1) % FUN_TIPS.length)
    }, 3000)
    return () => clearInterval(interval)
  }, [isWorking])

  if (!supervisor) return null

  // 获取主管的日志和流 - 支持动态实例ID
  const supervisorId = supervisor.id
  const logs = agentLogs[supervisorId] || []
  const streamContent = agentStreams[supervisorId] || ''
  
  // 从传入的数据中获取所有条目（已按 task 过滤）
  const allLogEntries = Object.values(agentLogs).flat()
  const allStreamContent = Object.values(agentStreams).filter(s => s && s.length > 0).join('\n---\n')
  
  // 优先使用当前主管实例的数据，否则使用所有传入数据（已按任务过滤）
  const effectiveLogs = logs.length > 0 ? logs : allLogEntries
  const effectiveStream = streamContent || allStreamContent
  
  // 统计数据
  const runningAgents = allAgents.filter(a => a.status === 'running' && a.role !== 'supervisor')
  const totalAgents = allAgents.filter(a => a.role !== 'supervisor')

  const tabs = [
    { key: 'overview', label: '📊 总览', icon: '📊' },
    { key: 'plan', label: '📋 计划', icon: '📋' },
    { key: 'team', label: '👥 团队', icon: '👥' },
    { key: 'thinking', label: '🧠 思考', icon: '🧠', badge: isWorking || effectiveStream.length > 0, canClear: effectiveStream.length > 0 },
    { key: 'logs', label: '📜 日志', icon: '📜', badge: effectiveLogs.length > 0, canClear: effectiveLogs.length > 0 },
  ]

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-[#0d1220] to-[#0a0e17] border-l border-purple-500/30">
      {/* CSS 动画 */}
      <style>{`
        @keyframes float-slow {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-5px); }
        }
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes rotate-slow {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>

      {/* 头部 - 增强版 */}
      <div className="p-4 border-b border-purple-500/20 bg-gradient-to-r from-purple-500/10 via-transparent to-pink-500/10">
        <div className="flex items-center gap-4">
          {/* 主管头像 - 增强动画 */}
          <div className="relative">
            <div className={`relative w-16 h-16 rounded-2xl flex items-center justify-center text-3xl transition-all duration-500 ${
              isWorking ? 'bg-gradient-to-br from-purple-500/40 to-pink-500/40' : 'bg-purple-500/15'
            }`}
            style={{ animation: isWorking ? 'float-slow 2s ease-in-out infinite' : undefined }}
            >
              {supervisor.avatar}
              {/* 工作状态光环 */}
              {isWorking && (
                <>
                  <div className="absolute -inset-1 rounded-2xl border-2 border-purple-400/50 animate-pulse" />
                  <div className="absolute -inset-2 rounded-2xl border border-purple-400/30" style={{ animation: 'rotate-slow 8s linear infinite' }} />
                </>
              )}
            </div>
            {/* 状态角标 */}
            <div className={`absolute -top-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center shadow-lg ${
              isWorking ? 'bg-gradient-to-br from-purple-500 to-pink-500' : 'bg-slate-600'
            }`}>
              <span className={`text-xs ${isWorking ? 'animate-spin' : ''}`}>{isWorking ? '⚙️' : '💤'}</span>
            </div>
          </div>
          
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-white">{supervisor.name}</h2>
              <span className={`px-3 py-1 rounded-full text-xs font-medium transition-all duration-500 ${
                isWorking 
                  ? 'bg-gradient-to-r from-purple-500/40 to-pink-500/40 text-purple-200 border border-purple-400/50' 
                  : 'bg-slate-700/50 text-slate-400 border border-slate-600/50'
              }`}>
                {isWorking ? '🧠 决策中' : '☕ 待命'}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">{supervisor.description}</p>
            {/* 心情状态 */}
            <p className="text-xs text-purple-300/70 mt-1 transition-all duration-500">
              {(isWorking ? SUPERVISOR_MOODS.working : SUPERVISOR_MOODS.idle)[moodIndex]}
            </p>
          </div>
          {onClose && (
            <button onClick={onClose} className="p-2 rounded-xl hover:bg-slate-700/50 text-slate-400 hover:text-white transition-all">
              ✕
            </button>
          )}
        </div>
        
        {/* 工作状态提示 - 增强版 */}
        {isWorking && (
          <div className="mt-4 p-3 rounded-xl bg-gradient-to-r from-purple-500/15 to-pink-500/15 border border-purple-500/40 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <div className="relative">
                <span className="text-2xl" style={{ animation: 'float-slow 1.5s ease-in-out infinite' }}>💭</span>
              </div>
              <div className="flex-1">
                <p className="text-sm text-purple-200 font-medium">
                  {THINKING_ANIMATIONS[thinkingIndex]}
                </p>
                <p className="text-xs text-purple-300/60 mt-1">
                  {FUN_TIPS[tipIndex]}
                </p>
              </div>
              {/* 进度指示器 */}
              <div className="flex gap-1">
                {[0, 1, 2].map(i => (
                  <div 
                    key={i} 
                    className="w-2 h-2 rounded-full bg-purple-400"
                    style={{ 
                      opacity: 0.3 + (((thinkingIndex + i) % 3) * 0.35),
                      animation: `pulse 1s ease-in-out ${i * 0.2}s infinite`
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Tab 导航 - 增强版 */}
      <div className="flex border-b border-purple-500/20 bg-gradient-to-r from-[#0a0e17]/80 to-[#0d1220]/80 backdrop-blur-sm">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            className={`relative flex-1 py-3.5 text-xs font-medium transition-all duration-300 ${
              activeTab === tab.key
                ? 'bg-gradient-to-b from-purple-500/25 to-transparent text-purple-200'
                : 'text-slate-500 hover:text-slate-300 hover:bg-purple-500/10'
            }`}
          >
            {/* 选中指示器 */}
            {activeTab === tab.key && (
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 bg-gradient-to-r from-purple-400 to-pink-400 rounded-full" />
            )}
            {tab.label}
            {tab.badge && (
              <span className="absolute top-1.5 right-2 w-2 h-2 rounded-full bg-purple-400 animate-pulse shadow-lg shadow-purple-400/50" />
            )}
          </button>
        ))}
        {/* 清除按钮 */}
        {onClearData && (effectiveStream.length > 0 || effectiveLogs.length > 0) && (
          <button
            onClick={onClearData}
            className="px-4 py-2 text-xs text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all rounded-lg m-1"
            title="清除思考和日志数据"
          >
            🗑️
          </button>
        )}
      </div>

      {/* Tab 内容 */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'overview' && (
          <OverviewTab 
            supervisor={supervisor} 
            currentTask={currentTask}
            runningAgents={runningAgents.length}
            totalAgents={totalAgents.length}
          />
        )}
        
        {activeTab === 'plan' && (
          <PlanTab currentTask={currentTask} />
        )}
        
        {activeTab === 'team' && (
          <TeamTab 
            allAgents={allAgents} 
            supervisor={supervisor}
          />
        )}
        
        {activeTab === 'thinking' && (
          <ThinkingTab 
            streamContent={effectiveStream}
            isWorking={isWorking}
          />
        )}
        
        {activeTab === 'logs' && (
          <LogsTab logs={effectiveLogs} />
        )}
      </div>
    </div>
  )
}

// 总览 Tab
function OverviewTab({ supervisor, currentTask, runningAgents, totalAgents }: {
  supervisor: Agent
  currentTask: Task | null
  runningAgents: number
  totalAgents: number
}) {
  const stats = supervisor.stats || { tasks_completed: 0, plans_created: 0, success_rate: 100 }
  
  return (
    <div className="p-4 space-y-4">
      {/* 当前任务 */}
      {currentTask && (
        <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30">
          <p className="text-xs text-slate-500 mb-1">📌 当前任务</p>
          <p className="text-sm text-cyan-300">{currentTask.content}</p>
          <div className="flex items-center gap-2 mt-2">
            <span className={`px-2 py-0.5 rounded text-xs ${
              currentTask.status === 'executing' ? 'bg-emerald-500/20 text-emerald-400' :
              currentTask.status === 'completed' ? 'bg-cyan-500/20 text-cyan-400' :
              'bg-slate-700 text-slate-400'
            }`}>
              {currentTask.status}
            </span>
            {currentTask.progress && (
              <span className="text-xs text-slate-500">
                进度: {currentTask.progress.percentage}%
              </span>
            )}
          </div>
        </div>
      )}

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard 
          icon="📋" 
          label="已规划任务" 
          value={stats.tasks_completed} 
          color="purple"
        />
        <StatCard 
          icon="✅" 
          label="成功率" 
          value={`${stats.success_rate || 100}%`} 
          color="emerald"
        />
        <StatCard 
          icon="👥" 
          label="活跃员工" 
          value={`${runningAgents}/${totalAgents}`} 
          color="cyan"
        />
        <StatCard 
          icon="⚡" 
          label="执行计划" 
          value={(stats as any).plans_created || stats.tasks_completed} 
          color="yellow"
        />
      </div>

      {/* 主管职责说明 */}
      <div className="p-3 rounded-xl bg-slate-800/30 border border-slate-700/50">
        <p className="text-xs text-slate-500 mb-2">🎯 主管职责</p>
        <div className="space-y-2">
          {[
            { icon: '🔍', text: '分析任务需求和复杂度' },
            { icon: '📚', text: '调研相关背景信息' },
            { icon: '📝', text: '改写和优化任务描述' },
            { icon: '📋', text: '制定详细执行计划' },
            { icon: '👥', text: '分配合适的团队成员' },
            { icon: '📊', text: '监控执行进度和质量' },
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-slate-400">
              <span>{item.icon}</span>
              <span>{item.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// 计划 Tab
function PlanTab({ currentTask }: { currentTask: Task | null }) {
  const plan = (currentTask as any)?.plan
  const executionPlan = plan?.execution_plan || []
  
  return (
    <div className="p-4 space-y-4">
      {plan ? (
        <>
          {/* 任务改写 */}
          {plan.refined_task && (
            <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/30">
              <p className="text-xs text-slate-500 mb-1">📝 优化后的任务</p>
              <p className="text-sm text-purple-300">{cleanThinkingTags(plan.refined_task)}</p>
            </div>
          )}

          {/* 关键目标 */}
          {plan.key_objectives && plan.key_objectives.length > 0 && (
            <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30">
              <p className="text-xs text-slate-500 mb-2">🎯 关键目标</p>
              <div className="space-y-1">
                {plan.key_objectives.map((obj: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-cyan-300">
                    <span className="text-cyan-500">•</span>
                    <span>{cleanThinkingTags(obj)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 执行步骤 */}
          {executionPlan.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">📋 执行计划 ({executionPlan.length} 步)</p>
              {executionPlan.map((step: any, i: number) => (
                <div key={i} className="p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-full bg-purple-500/20 flex items-center justify-center text-xs text-purple-400">
                      {i + 1}
                    </span>
                    <span className="text-sm text-white flex-1">{cleanThinkingTags(step.name || step.description)}</span>
                    {step.agent_type && (
                      <span className="px-2 py-0.5 rounded text-xs bg-cyan-500/20 text-cyan-400">
                        {step.agent_type}
                      </span>
                    )}
                  </div>
                  {step.description && step.name && (
                    <p className="text-xs text-slate-400 mt-1 ml-8">{cleanThinkingTags(step.description)}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 text-slate-500">
          <span className="text-4xl mb-3">📋</span>
          <p className="text-sm">暂无执行计划</p>
          <p className="text-xs mt-1">等待主管分析任务...</p>
        </div>
      )}
    </div>
  )
}

// 团队 Tab
function TeamTab({ allAgents, supervisor }: { allAgents: Agent[]; supervisor: Agent }) {
  const workers = allAgents.filter(a => a.role !== 'supervisor' && a.role !== 'quality_checker')
  const runningWorkers = workers.filter(a => a.status === 'running')
  const idleWorkers = workers.filter(a => a.status !== 'running')
  
  return (
    <div className="p-4 space-y-4">
      {/* 团队概览 */}
      <div className="p-3 rounded-xl bg-slate-800/30 border border-slate-700/50">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">团队规模</span>
          <span className="text-sm text-white">{workers.length} 名员工</span>
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-slate-500">工作中</span>
          <span className="text-sm text-emerald-400">{runningWorkers.length} 人</span>
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-slate-500">待命中</span>
          <span className="text-sm text-slate-400">{idleWorkers.length} 人</span>
        </div>
      </div>

      {/* 工作中的员工 */}
      {runningWorkers.length > 0 && (
        <div>
          <p className="text-xs text-emerald-400 mb-2 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            正在工作 ({runningWorkers.length})
          </p>
          <div className="space-y-2 max-h-32 overflow-auto">
            {runningWorkers.map(agent => (
              <MiniAgentCard key={agent.id} agent={agent} isWorking />
            ))}
          </div>
        </div>
      )}

      {/* 待命中的员工 */}
      {idleWorkers.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 mb-2 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-slate-500" />
            待命中 ({idleWorkers.length})
          </p>
          <div className="space-y-1 max-h-48 overflow-auto">
            {idleWorkers.slice(0, 15).map(agent => (
              <MiniAgentCard key={agent.id} agent={agent} />
            ))}
            {idleWorkers.length > 15 && (
              <p className="text-xs text-slate-500 text-center py-1">
                还有 {idleWorkers.length - 15} 人...
              </p>
            )}
          </div>
        </div>
      )}

      {/* 可调度能力 */}
      <div>
        <p className="text-xs text-slate-500 mb-2">🔧 可调度能力</p>
        <div className="flex flex-wrap gap-1">
          {supervisor.tools.map(tool => (
            <span key={tool} className="px-2 py-1 text-xs rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
              {tool}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

// 思考 Tab - 增强版
function ThinkingTab({ streamContent, isWorking }: { streamContent: string; isWorking: boolean }) {
  // 解析思考内容
  const parseThinking = (content: string) => {
    if (!content) return { thoughts: [], normalContent: '' }
    
    // 将所有 [THINKING]...[/THINKING] 块的内容拼接为一个完整的思考流
    // 不做 trim，保留原始换行，这样流式输出的换行不会丢失
    let thinkingStream = ''
    let remaining = content
    let normalContent = ''
    
    while (remaining.length > 0) {
      const startIdx = remaining.search(/\[THINKING\]/i)
      
      if (startIdx === -1) {
        normalContent += remaining
        break
      }
      
      if (startIdx > 0) {
        normalContent += remaining.slice(0, startIdx)
      }
      
      const endIdx = remaining.search(/\[\/THINKING\]/i)
      
      if (endIdx === -1 || endIdx < startIdx) {
        // 未闭合的 thinking 块（正在流式输出中）
        thinkingStream += remaining.slice(startIdx + 10)
        break
      }
      
      // 拼接 thinking 内容，保留原始换行
      thinkingStream += remaining.slice(startIdx + 10, endIdx)
      remaining = remaining.slice(endIdx + 11)
    }
    
    // 清理 normalContent 中残留的标签
    normalContent = normalContent
      .replace(/\[THINKING\]/gi, '')
      .replace(/\[\/THINKING\]/gi, '')
      .replace(/\[NEW_PHASE\]/gi, '\n---\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    
    // 将完整的思考流按段落分割显示
    const trimmedThinking = thinkingStream.replace(/^\n+/, '').replace(/\n+$/, '')
    const thoughts = trimmedThinking ? [trimmedThinking] : []
    
    return { thoughts, normalContent }
  }
  
  const { thoughts, normalContent } = parseThinking(streamContent)
  const hasContent = thoughts.length > 0 || normalContent.length > 0
  
  return (
    <div className="p-4 space-y-4 overflow-auto h-full">
      {hasContent ? (
        <>
          {/* 深度思考 - 增强版 */}
          {thoughts.length > 0 && (
            <div className="p-4 rounded-2xl bg-gradient-to-br from-purple-500/15 to-pink-500/10 border border-purple-500/40 backdrop-blur-sm">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-lg bg-purple-500/30 flex items-center justify-center">
                  <span className="text-lg">🧠</span>
                </div>
                <span className="text-sm text-purple-300 font-semibold">深度思考</span>
                {isWorking && (
                  <span className="px-2 py-0.5 rounded-full text-xs bg-purple-500/30 text-purple-200 animate-pulse">
                    ⚡ 实时
                  </span>
                )}
                <div className="flex-1 h-px bg-gradient-to-r from-purple-500/40 to-transparent" />
              </div>
              <div className="max-h-[300px] overflow-auto space-y-3 pr-2">
                {thoughts.map((thought, i) => (
                  <div key={i} className="relative pl-4 border-l-2 border-purple-400/50">
                    <pre 
                      className="text-xs text-purple-200/90 whitespace-pre-wrap break-words font-sans leading-relaxed"
                      style={{ wordBreak: 'break-word' }}
                    >
                      {thought}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 输出内容 - 增强版 */}
          {normalContent && (
            <div className="p-4 rounded-2xl bg-gradient-to-br from-cyan-500/15 to-emerald-500/10 border border-cyan-500/40 backdrop-blur-sm">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/30 flex items-center justify-center">
                  <span className="text-lg">💬</span>
                </div>
                <span className="text-sm text-cyan-300 font-semibold">输出结果</span>
                <div className="flex-1 h-px bg-gradient-to-r from-cyan-500/40 to-transparent" />
              </div>
              <pre 
                className="text-xs text-cyan-200 whitespace-pre-wrap break-words font-sans leading-relaxed max-h-[300px] overflow-auto"
                style={{ wordBreak: 'break-word' }}
              >
                {normalContent}
              </pre>
            </div>
          )}
        </>
      ) : isWorking ? (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="relative">
            {/* 外圈 */}
            <div className="w-24 h-24 rounded-full border-4 border-purple-500/20" />
            {/* 旋转圈 */}
            <div 
              className="absolute inset-0 w-24 h-24 rounded-full border-4 border-transparent border-t-purple-500 border-r-purple-400"
              style={{ animation: 'spin 1.5s linear infinite' }}
            />
            {/* 中心图标 */}
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-4xl" style={{ animation: 'pulse 2s ease-in-out infinite' }}>🧠</span>
            </div>
          </div>
          <p className="text-base text-purple-300 mt-6 font-medium">主管正在深度思考...</p>
          <p className="text-xs text-purple-400/60 mt-2">请稍候，灵感即将涌现</p>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-16 text-slate-500">
          <div className="w-20 h-20 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-4">
            <span className="text-4xl">💭</span>
          </div>
          <p className="text-sm font-medium">主管当前空闲</p>
          <p className="text-xs mt-2 text-slate-600">等待新任务分配...</p>
        </div>
      )}
    </div>
  )
}

// 日志 Tab
function LogsTab({ logs }: { logs: Array<{ timestamp: string; message: string; level: string }> }) {
  // 清理并过滤日志
  const cleanedLogs = useMemo(() => {
    return logs
      .map(log => ({
        ...log,
        message: cleanThinkingTags(log.message)
      }))
      .filter(log => log.message.length > 0) // 过滤空消息
  }, [logs])

  return (
    <div className="p-4">
      {cleanedLogs.length > 0 ? (
        <div className="space-y-2">
          {cleanedLogs.slice(-50).map((log, i) => (
            <div key={i} className={`text-xs p-2 rounded-lg ${
              log.level === 'error' ? 'bg-red-500/10 text-red-400' :
              log.level === 'success' ? 'bg-emerald-500/10 text-emerald-400' :
              log.level === 'warning' ? 'bg-yellow-500/10 text-yellow-400' :
              'bg-slate-800/50 text-slate-300'
            }`}>
              <span className="text-slate-500 mr-2">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span className="whitespace-pre-wrap">{log.message}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 text-slate-500">
          <span className="text-4xl mb-3">📜</span>
          <p className="text-sm">暂无日志</p>
        </div>
      )}
    </div>
  )
}

// 统计卡片
function StatCard({ icon, label, value, color }: { 
  icon: string
  label: string
  value: string | number
  color: 'purple' | 'emerald' | 'cyan' | 'yellow'
}) {
  const colorClasses = {
    purple: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    cyan: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400',
    yellow: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
  }
  
  return (
    <div className={`p-3 rounded-xl border ${colorClasses[color]}`}>
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <div>
          <p className="text-xs text-slate-500">{label}</p>
          <p className="text-lg font-bold">{value}</p>
        </div>
      </div>
    </div>
  )
}

// 迷你员工卡片
function MiniAgentCard({ agent, isWorking = false }: { agent: Agent; isWorking?: boolean }) {
  return (
    <div className={`p-2 rounded-lg flex items-center gap-2 ${
      isWorking 
        ? 'bg-emerald-500/10 border border-emerald-500/30' 
        : 'bg-slate-800/30 border border-slate-700/30'
    }`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-lg ${
        isWorking ? 'bg-emerald-500/20' : 'bg-slate-700/50'
      }`}>
        {agent.avatar}
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-xs truncate ${isWorking ? 'text-white' : 'text-slate-400'}`}>
          {agent.name}
        </p>
        {agent.current_task ? (
          <p className="text-[10px] text-emerald-400 truncate">⚡ {agent.current_task}</p>
        ) : (
          <p className="text-[10px] text-slate-500 truncate">{agent.role}</p>
        )}
      </div>
      <div className={`w-2 h-2 rounded-full ${isWorking ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
    </div>
  )
}
