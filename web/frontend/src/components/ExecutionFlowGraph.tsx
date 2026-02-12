import { useState } from 'react'
import type { SubTaskNode, ExecutionFlowGraph as FlowGraphType, WaveExecutionResult } from '../types'

interface Props {
  flow: FlowGraphType | null
  onStepClick: (step: SubTaskNode) => void
}

// 状态颜色映射
const statusColors: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  pending: { bg: 'bg-slate-800', border: 'border-slate-600', text: 'text-slate-400', glow: '' },
  waiting: { bg: 'bg-yellow-900/30', border: 'border-yellow-500/50', text: 'text-yellow-400', glow: '' },
  blocked: { bg: 'bg-orange-900/30', border: 'border-orange-500/50', text: 'text-orange-400', glow: '' },
  running: { bg: 'bg-cyan-500/20', border: 'border-cyan-500', text: 'text-cyan-400', glow: 'shadow-lg shadow-cyan-500/30 animate-pulse' },
  completed: { bg: 'bg-emerald-500/20', border: 'border-emerald-500', text: 'text-emerald-400', glow: '' },
  failed: { bg: 'bg-red-500/20', border: 'border-red-500', text: 'text-red-400', glow: '' },
  skipped: { bg: 'bg-slate-700/50', border: 'border-slate-500', text: 'text-slate-500', glow: '' },
}

// Agent 类型图标
const agentIcons: Record<string, string> = {
  searcher: '🔍',
  analyst: '📊',
  fact_checker: '✅',
  writer: '✍️',
  translator: '🌐',
  coder: '💻',
  researcher: '🔬',
  summarizer: '📝',
  supervisor: '👔',
}

// 状态图标
const statusIcons: Record<string, string> = {
  pending: '⏸️',
  waiting: '⏳',
  blocked: '🚫',
  running: '🔄',
  completed: '✅',
  failed: '❌',
  skipped: '⏭️',
}

// 波次统计面板
function WaveStatsPanel({ waveExecution }: { waveExecution: WaveExecutionResult }) {
  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`
  }

  return (
    <div className="px-4 py-3 border-b border-cyan-500/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs text-cyan-400 font-medium">⚡ 波次执行统计</span>
        <span className="text-[10px] text-slate-500">
          {formatTime(waveExecution.total_execution_time)}
        </span>
      </div>
      
      {/* 总览 */}
      <div className="grid grid-cols-4 gap-2 mb-2">
        <MiniStat label="波次" value={waveExecution.total_waves} color="text-cyan-400" />
        <MiniStat label="完成" value={waveExecution.completed_tasks} color="text-emerald-400" />
        <MiniStat label="失败" value={waveExecution.failed_tasks} color="text-red-400" />
        <MiniStat label="阻塞" value={waveExecution.blocked_tasks} color="text-orange-400" />
      </div>

      {/* 波次时间线 */}
      {waveExecution.wave_stats && waveExecution.wave_stats.length > 0 && (
        <div className="flex gap-1 items-end h-8">
          {waveExecution.wave_stats.map((ws) => {
            const duration = ws.end_time - ws.start_time
            const maxDuration = Math.max(...waveExecution.wave_stats!.map(s => s.end_time - s.start_time), 1)
            const height = Math.max(20, (duration / maxDuration) * 100)
            const allCompleted = ws.completed_tasks === ws.task_count
            const hasFailed = ws.failed_tasks > 0
            
            return (
              <div
                key={ws.wave_number}
                className="flex-1 group relative"
                title={`波次 ${ws.wave_number + 1}: ${ws.task_count} 任务, 并行度 ${ws.parallelism}, ${formatTime(duration)}`}
              >
                <div
                  className={`rounded-sm transition-all ${
                    hasFailed ? 'bg-red-500/60' : allCompleted ? 'bg-emerald-500/60' : 'bg-cyan-500/40'
                  } hover:opacity-80`}
                  style={{ height: `${height}%`, minHeight: '4px' }}
                />
                <div className="text-[8px] text-center text-slate-500 mt-0.5">
                  W{ws.wave_number + 1}
                </div>
                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10">
                  <div className="bg-slate-900 border border-slate-700 rounded-lg p-2 text-[10px] whitespace-nowrap shadow-xl">
                    <p className="text-cyan-400">波次 {ws.wave_number + 1}</p>
                    <p className="text-slate-400">{ws.task_count} 任务 · 并行 {ws.parallelism}</p>
                    <p className="text-slate-400">{formatTime(duration)}</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function MiniStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="text-center">
      <p className={`text-sm font-semibold ${color}`}>{value}</p>
      <p className="text-[9px] text-slate-500">{label}</p>
    </div>
  )
}

export default function ExecutionFlowGraph({ flow, onStepClick }: Props) {
  const [hoveredStep, setHoveredStep] = useState<string | null>(null)

  if (!flow || Object.keys(flow.steps).length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        <div className="text-center">
          <div className="text-4xl mb-3">📊</div>
          <p>暂无执行流程</p>
          <p className="text-xs mt-1">任务开始后将显示执行流程图</p>
        </div>
      </div>
    )
  }

  // 按执行顺序排列步骤
  const orderedSteps = flow.execution_order
    .map(id => flow.steps[id])
    .filter(Boolean)

  const steps = orderedSteps.length > 0 
    ? orderedSteps 
    : Object.values(flow.steps).sort((a, b) => a.step_number - b.step_number)

  return (
    <div className="h-full flex flex-col">
      {/* 波次统计面板 */}
      {flow.wave_execution && flow.wave_execution.total_waves > 0 && (
        <WaveStatsPanel waveExecution={flow.wave_execution} />
      )}

      {/* 进度条 */}
      <div className="px-4 py-3 border-b border-cyan-500/20">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-400">执行进度</span>
          <span className="text-xs text-cyan-400">{flow.progress.progress_percent}%</span>
        </div>
        <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all duration-500"
            style={{ width: `${flow.progress.progress_percent}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-[10px] text-slate-500">
          <span>完成: {flow.progress.completed}</span>
          <span>执行中: {flow.progress.running}</span>
          <span>失败: {flow.progress.failed}</span>
          <span>总计: {flow.progress.total}</span>
        </div>
      </div>

      {/* 流程图 */}
      <div className="flex-1 overflow-auto p-4">
        <div className="relative min-h-full">
          {/* 连接线 */}
          <div className="absolute left-8 top-0 bottom-0 w-px bg-gradient-to-b from-cyan-500/30 via-purple-500/30 to-emerald-500/30" />

          {/* 步骤节点 */}
          <div className="space-y-4">
            {steps.map((step) => {
              const colors = statusColors[step.status] || statusColors.pending
              const isHovered = hoveredStep === step.step_id
              const hasDeps = step.dependencies.length > 0

              return (
                <div
                  key={step.step_id}
                  className="relative"
                  onMouseEnter={() => setHoveredStep(step.step_id)}
                  onMouseLeave={() => setHoveredStep(null)}
                >
                  {hasDeps && (
                    <div className="absolute left-6 -top-2 w-4 h-4 flex items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-purple-500/50" />
                    </div>
                  )}

                  <div
                    onClick={() => onStepClick(step)}
                    className={`
                      relative ml-12 p-4 rounded-xl border-2 cursor-pointer
                      transition-all duration-200 hover:scale-[1.02]
                      ${colors.bg} ${colors.border} ${colors.glow}
                      ${isHovered ? 'ring-2 ring-cyan-500/50' : ''}
                    `}
                  >
                    <div className={`
                      absolute -left-[26px] top-1/2 -translate-y-1/2
                      w-6 h-6 rounded-full border-2 flex items-center justify-center
                      ${colors.bg} ${colors.border}
                    `}>
                      <span className="text-sm">{statusIcons[step.status]}</span>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className={`
                        w-10 h-10 rounded-lg flex items-center justify-center text-xl
                        ${step.status === 'running' ? 'bg-cyan-500/30 animate-pulse' : 'bg-slate-700/50'}
                      `}>
                        {agentIcons[step.agent_type] || '🤖'}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`font-medium ${colors.text}`}>
                            {step.step_number}. {step.name}
                          </span>
                          <span className={`
                            px-2 py-0.5 rounded-full text-[10px]
                            ${colors.bg} ${colors.text} border ${colors.border}
                          `}>
                            {step.status}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                          {step.description}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 pt-3 border-t border-slate-700/50">
                      <div className="flex items-center gap-4 text-[10px]">
                        <div className="flex items-center gap-1">
                          <span className="text-slate-500">执行者:</span>
                          <span className="text-purple-400">
                            {step.agent_name || step.agent_type}
                          </span>
                        </div>
                        {step.dependencies.length > 0 && (
                          <div className="flex items-center gap-1">
                            <span className="text-slate-500">依赖:</span>
                            <span className="text-cyan-400">
                              {step.dependencies.join(', ')}
                            </span>
                          </div>
                        )}
                      </div>
                      {step.expected_output && (
                        <div className="mt-2 text-[10px]">
                          <span className="text-slate-500">预期产出: </span>
                          <span className="text-slate-400">{step.expected_output}</span>
                        </div>
                      )}
                      {step.error && (
                        <div className="mt-2 p-2 rounded-lg bg-red-500/10 border border-red-500/30">
                          <p className="text-[10px] text-red-400">❌ {step.error}</p>
                        </div>
                      )}
                      {step.started_at && (
                        <div className="mt-2 flex gap-4 text-[10px] text-slate-500">
                          <span>开始: {step.started_at}</span>
                          {step.completed_at && <span>完成: {step.completed_at}</span>}
                        </div>
                      )}
                    </div>

                    {isHovered && (
                      <div className="absolute right-3 top-3 text-[10px] text-cyan-400">
                        点击查看详情 →
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

// 步骤详情弹窗组件
export function StepDetailModal({ 
  step, 
  onClose 
}: { 
  step: SubTaskNode | null
  onClose: () => void 
}) {
  if (!step) return null

  const colors = statusColors[step.status] || statusColors.pending

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div 
        className="bg-[#0a0e17] border border-cyan-500/30 rounded-2xl w-[700px] max-h-[85vh] shadow-2xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className={`p-5 border-b ${colors.border} flex items-center gap-4`}>
          <div className={`
            w-14 h-14 rounded-xl flex items-center justify-center text-2xl
            ${step.status === 'running' ? 'bg-cyan-500/30 animate-pulse' : 'bg-slate-700/50'}
          `}>
            {agentIcons[step.agent_type] || '🤖'}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold">{step.step_number}. {step.name}</h2>
              <span className={`
                px-3 py-1 rounded-full text-xs
                ${colors.bg} ${colors.text} border ${colors.border}
              `}>
                {statusIcons[step.status]} {step.status}
              </span>
            </div>
            <p className="text-sm text-slate-400 mt-1">{step.description}</p>
          </div>
          <button 
            onClick={onClose} 
            className="text-slate-400 hover:text-white text-xl p-2"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <InfoCard label="执行智能体" value={step.agent_name || step.agent_type} icon={agentIcons[step.agent_type]} />
            <InfoCard label="步骤ID" value={step.step_id} />
            <InfoCard label="开始时间" value={step.started_at || '未开始'} />
            <InfoCard label="完成时间" value={step.completed_at || '未完成'} />
          </div>

          {step.dependencies.length > 0 && (
            <div className="p-4 rounded-xl bg-purple-500/10 border border-purple-500/30">
              <h3 className="text-sm text-purple-400 mb-2">📎 依赖步骤</h3>
              <div className="flex flex-wrap gap-2">
                {step.dependencies.map(dep => (
                  <span key={dep} className="px-3 py-1 rounded-lg bg-purple-500/20 text-purple-300 text-xs">
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="p-4 rounded-xl bg-cyan-500/10 border border-cyan-500/30">
            <h3 className="text-sm text-cyan-400 mb-2">🎯 预期产出</h3>
            <p className="text-sm text-slate-300">{step.expected_output || '未指定'}</p>
          </div>

          {step.output_data && (
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
              <h3 className="text-sm text-emerald-400 mb-2">📤 输出结果</h3>
              <pre className="text-xs text-slate-300 whitespace-pre-wrap overflow-auto max-h-40 bg-slate-800/50 p-3 rounded-lg">
                {typeof step.output_data === 'string' 
                  ? step.output_data 
                  : JSON.stringify(step.output_data, null, 2)}
              </pre>
            </div>
          )}

          {step.error && (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30">
              <h3 className="text-sm text-red-400 mb-2">❌ 错误信息</h3>
              <p className="text-sm text-red-300">{step.error}</p>
            </div>
          )}

          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700">
            <h3 className="text-sm text-slate-400 mb-3">📋 执行日志</h3>
            <div className="space-y-2 max-h-60 overflow-auto">
              {step.logs && step.logs.length > 0 ? (
                step.logs.map((log, i) => (
                  <div 
                    key={i} 
                    className={`
                      text-xs p-2 rounded-lg
                      ${log.level === 'error' ? 'bg-red-500/10 text-red-400' : 
                        log.level === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 
                        'bg-slate-700/50 text-slate-300'}
                    `}
                  >
                    <span className="text-slate-500 mr-2">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                    {log.message}
                  </div>
                ))
              ) : (
                <p className="text-slate-500 text-xs text-center py-4">暂无执行日志</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function InfoCard({ label, value, icon }: { label: string; value: string; icon?: string }) {
  return (
    <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700">
      <p className="text-[10px] text-slate-500 mb-1">{label}</p>
      <p className="text-sm text-slate-200 flex items-center gap-2">
        {icon && <span>{icon}</span>}
        {value}
      </p>
    </div>
  )
}
