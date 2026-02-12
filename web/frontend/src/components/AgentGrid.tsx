import { motion } from 'framer-motion'
import { Users } from 'lucide-react'
import { AgentCard } from './AgentCard'
import type { Agent } from '../types'

interface AgentGridProps {
  agents: Agent[]
}

export function AgentGrid({ agents }: AgentGridProps) {
  const runningAgents = agents.filter(a => a.status === 'running')
  const idleAgents = agents.filter(a => a.status === 'idle')

  return (
    <div className="h-full flex flex-col">
      {/* 标题 */}
      <div className="p-4 border-b border-cyan-500/20 flex items-center gap-3">
        <div className="p-2 rounded-lg bg-purple-500/10">
          <Users className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h2 className="font-semibold text-white">AI 员工团队</h2>
          <p className="text-xs text-gray-500">
            {runningAgents.length} 人工作中 / {agents.length} 人总计
          </p>
        </div>
      </div>

      {/* 员工网格 */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* 工作中的员工 */}
        {runningAgents.length > 0 && (
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-emerald-400 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              正在工作
            </h3>
            <motion.div 
              layout
              className="grid grid-cols-1 xl:grid-cols-2 gap-4"
            >
              {runningAgents.map((agent) => (
                <AgentCard key={agent.id} agent={agent} />
              ))}
            </motion.div>
          </div>
        )}

        {/* 空闲员工 */}
        <div>
          <h3 className="text-xs font-semibold text-gray-500 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-gray-500" />
            待命中
          </h3>
          <motion.div 
            layout
            className="grid grid-cols-1 xl:grid-cols-2 gap-4"
          >
            {idleAgents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </motion.div>
        </div>
      </div>
    </div>
  )
}
