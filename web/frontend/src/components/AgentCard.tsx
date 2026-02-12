import { motion } from 'framer-motion'
import { Wrench } from 'lucide-react'
import type { Agent } from '../types'

interface AgentCardProps {
  agent: Agent
}

export function AgentCard({ agent }: AgentCardProps) {
  const statusColors: Record<string, string> = {
    idle: 'border-gray-600',
    running: 'border-emerald-500 shadow-lg shadow-emerald-500/20',
    completed: 'border-cyan-500',
    failed: 'border-red-500',
  }

  const statusBg: Record<string, string> = {
    idle: 'bg-gray-600/20',
    running: 'bg-emerald-500/20',
    completed: 'bg-cyan-500/20',
    failed: 'bg-red-500/20',
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`
        relative p-4 rounded-xl glass
        border ${statusColors[agent.status] || 'border-gray-600'}
        transition-all duration-300
      `}
    >
      {/* 扫描线效果 */}
      {agent.status === 'running' && (
        <div className="absolute inset-0 overflow-hidden rounded-xl">
          <div className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-emerald-400 to-transparent animate-scan" />
        </div>
      )}

      <div className="flex items-start gap-3">
        {/* 头像 */}
        <div className={`
          w-12 h-12 rounded-xl flex items-center justify-center text-2xl
          ${statusBg[agent.status] || 'bg-gray-600/20'}
          ${agent.status === 'running' ? 'animate-bounce' : ''}
        `}>
          {agent.avatar}
        </div>

        <div className="flex-1 min-w-0">
          {/* 名称和状态 */}
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-white truncate">{agent.name}</h3>
            <div className={`status-dot ${agent.status}`} />
          </div>

          {/* 描述 */}
          <p className="text-xs text-gray-400 mt-0.5 truncate">
            {agent.description}
          </p>

          {/* 当前任务 */}
          {agent.current_task && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-2 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30"
            >
              <p className="text-xs text-emerald-400 truncate">
                ⚡ {agent.current_task}
              </p>
            </motion.div>
          )}

          {/* 工具列表 */}
          <div className="flex items-center gap-1 mt-2 flex-wrap">
            <Wrench className="w-3 h-3 text-gray-500" />
            {agent.tools.slice(0, 3).map((tool) => (
              <span
                key={tool}
                className="px-1.5 py-0.5 text-[10px] rounded bg-purple-500/10 text-purple-400"
              >
                {tool}
              </span>
            ))}
            {agent.tools.length > 3 && (
              <span className="text-[10px] text-gray-500">
                +{agent.tools.length - 3}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 统计数据 */}
      {agent.stats && (
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-700/50">
          <div className="text-center">
            <p className="text-xs text-gray-500">完成任务</p>
            <p className="font-cyber text-sm text-cyan-400">
              {agent.stats.tasks_completed}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-gray-500">成功率</p>
            <p className="font-cyber text-sm text-emerald-400">
              {agent.stats.success_rate}%
            </p>
          </div>
        </div>
      )}
    </motion.div>
  )
}
