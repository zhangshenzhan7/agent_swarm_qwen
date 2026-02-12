import { motion } from 'framer-motion'
import { 
  Search, 
  GitBranch, 
  Users, 
  Zap, 
  Layers,
  CheckCircle,
  Loader2,
} from 'lucide-react'
import type { Task } from '../types'

interface ExecutionFlowProps {
  task: Task | null
}

const stages = [
  { key: 'analyzing', name: '任务分析', icon: Search, colorClass: 'bg-cyan-500/20 border-cyan-500 text-cyan-400' },
  { key: 'decomposing', name: '任务分解', icon: GitBranch, colorClass: 'bg-purple-500/20 border-purple-500 text-purple-400' },
  { key: 'assigning', name: '智能体分配', icon: Users, colorClass: 'bg-pink-500/20 border-pink-500 text-pink-400' },
  { key: 'executing', name: '并行执行', icon: Zap, colorClass: 'bg-emerald-500/20 border-emerald-500 text-emerald-400' },
  { key: 'aggregating', name: '结果聚合', icon: Layers, colorClass: 'bg-yellow-500/20 border-yellow-500 text-yellow-400' },
]

export function ExecutionFlow({ task }: ExecutionFlowProps) {
  const getStageStatus = (index: number) => {
    if (!task) return 'pending'
    const stage = task.stages[index]
    return stage?.status || 'pending'
  }

  return (
    <div className="p-6">
      <h3 className="font-cyber text-sm text-gray-400 mb-6">执行流程</h3>
      
      <div className="relative">
        {/* 连接线 */}
        <div className="absolute left-6 top-0 bottom-0 w-px bg-gradient-to-b from-cyan-500/50 via-purple-500/50 to-emerald-500/50" />
        
        {/* 阶段节点 */}
        <div className="space-y-6">
          {stages.map((stage, index) => {
            const status = getStageStatus(index)
            const Icon = stage.icon
            
            const nodeClass = status === 'running' 
              ? `${stage.colorClass} border-2 animate-pulse`
              : status === 'completed'
              ? 'bg-emerald-500/20 border-2 border-emerald-500'
              : status === 'failed'
              ? 'bg-red-500/20 border-2 border-red-500'
              : 'bg-gray-800 border border-gray-600'
            
            const iconClass = status === 'running'
              ? stage.colorClass.split(' ').pop() || 'text-cyan-400'
              : status === 'completed'
              ? 'text-emerald-400'
              : status === 'failed'
              ? 'text-red-400'
              : 'text-gray-500'
            
            return (
              <motion.div
                key={stage.key}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                className="relative flex items-center gap-4"
              >
                {/* 节点图标 */}
                <div className={`relative z-10 w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-300 ${nodeClass}`}>
                  {status === 'running' ? (
                    <Loader2 className={`w-5 h-5 animate-spin ${iconClass}`} />
                  ) : status === 'completed' ? (
                    <CheckCircle className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <Icon className={`w-5 h-5 ${iconClass}`} />
                  )}
                </div>

                {/* 阶段信息 */}
                <div className="flex-1">
                  <p className={`font-medium ${
                    status === 'running' ? 'text-white' :
                    status === 'completed' ? 'text-emerald-400' :
                    status === 'failed' ? 'text-red-400' : 'text-gray-500'
                  }`}>
                    {stage.name}
                  </p>
                  
                  {task?.stages[index]?.details && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      {task.stages[index].details}
                    </p>
                  )}
                </div>

                {/* 状态指示 */}
                {status === 'running' && (
                  <motion.div
                    animate={{ scale: [1, 1.2, 1] }}
                    transition={{ repeat: Infinity, duration: 1.5 }}
                    className="w-3 h-3 rounded-full bg-cyan-400"
                  />
                )}
              </motion.div>
            )
          })}
        </div>
      </div>

      {/* 完成状态 */}
      {task?.status === 'completed' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-8 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30"
        >
          <div className="flex items-center gap-3">
            <CheckCircle className="w-6 h-6 text-emerald-400" />
            <div>
              <p className="font-semibold text-emerald-400">任务完成</p>
              <p className="text-xs text-gray-400 mt-0.5">
                所有阶段已成功执行
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  )
}
