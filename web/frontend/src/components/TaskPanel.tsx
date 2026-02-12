import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Clock, CheckCircle, XCircle, Loader2, ChevronRight, Trash2 } from 'lucide-react'
import type { Task, ExecutionStage } from '../types'
import { ArtifactPanel } from './ArtifactPanel'
import { DownloadAllButton } from './DownloadButton'

interface TaskPanelProps {
  tasks: Task[]
  onCreateTask: (content: string) => void
  onDeleteTask: (taskId: string) => void
  selectedTask: Task | null
  onSelectTask: (task: Task) => void
}

export function TaskPanel({ tasks, onCreateTask, onDeleteTask, selectedTask, onSelectTask }: TaskPanelProps) {
  const [input, setInput] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim()) {
      onCreateTask(input.trim())
      setInput('')
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* 任务输入 */}
      <form onSubmit={handleSubmit} className="p-4 border-b border-cyan-500/20">
        <div className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入任务描述，让 AI 员工帮你完成..."
            className="w-full px-4 py-3 pr-12 rounded-xl bg-[#0a0e17] border border-cyan-500/30 
                       text-white placeholder-gray-500 focus:outline-none focus:border-cyan-400
                       transition-colors"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg
                       bg-gradient-to-r from-cyan-500 to-purple-500
                       disabled:opacity-50 disabled:cursor-not-allowed
                       hover:shadow-lg hover:shadow-cyan-500/30 transition-all"
          >
            <Send className="w-4 h-4 text-white" />
          </button>
        </div>
      </form>

      {/* 任务列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <AnimatePresence>
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              isSelected={selectedTask?.id === task.id}
              onClick={() => onSelectTask(task)}
              onDelete={() => onDeleteTask(task.id)}
            />
          ))}
        </AnimatePresence>

        {tasks.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-sm">暂无任务</p>
            <p className="text-xs mt-1">输入任务描述开始工作</p>
          </div>
        )}
      </div>
    </div>
  )
}

interface TaskCardProps {
  task: Task
  isSelected: boolean
  onClick: () => void
  onDelete: () => void
}

function TaskCard({ task, isSelected, onClick, onDelete }: TaskCardProps) {
  const statusIcons: Record<string, JSX.Element> = {
    pending: <Clock className="w-4 h-4 text-gray-400" />,
    analyzing: <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />,
    decomposing: <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />,
    executing: <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />,
    aggregating: <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />,
    completed: <CheckCircle className="w-4 h-4 text-emerald-400" />,
    failed: <XCircle className="w-4 h-4 text-red-500" />,
    cancelled: <XCircle className="w-4 h-4 text-gray-500" />,
  }

  const statusColors: Record<string, string> = {
    pending: 'border-gray-600',
    analyzing: 'border-cyan-500',
    decomposing: 'border-purple-500',
    executing: 'border-emerald-500',
    aggregating: 'border-yellow-500',
    completed: 'border-emerald-500',
    failed: 'border-red-500',
    cancelled: 'border-gray-500',
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      onClick={onClick}
      className={`
        p-4 rounded-xl glass cursor-pointer
        border ${statusColors[task.status] || 'border-gray-600'}
        ${isSelected ? 'ring-2 ring-cyan-500' : ''}
        hover:border-cyan-500/50 transition-all
      `}
    >
      <div className="flex items-start gap-3">
        {statusIcons[task.status] || statusIcons.pending}
        
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white truncate">{task.content}</p>
          <p className="text-xs text-gray-500 mt-1">
            {new Date(task.created_at).toLocaleString('zh-CN')}
          </p>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="p-1.5 rounded-lg hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-colors"
            title="删除任务"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <ChevronRight className="w-4 h-4 text-gray-500" />
        </div>
      </div>

      {/* 进度条 */}
      {task.progress && task.progress.percentage > 0 && task.progress.percentage < 100 && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-gray-400">{task.progress.current_stage}</span>
            <span className="text-cyan-400">{task.progress.percentage}%</span>
          </div>
          <div className="h-1 rounded-full bg-gray-700 overflow-hidden">
            <motion.div
              className="h-full progress-bar"
              initial={{ width: 0 }}
              animate={{ width: `${task.progress.percentage}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>
      )}
    </motion.div>
  )
}

// 任务详情面板
interface TaskDetailProps {
  task: Task
  logs: Array<{ timestamp: string; message: string; level: string }>
}

export function TaskDetail({ task, logs }: TaskDetailProps) {
  return (
    <div className="h-full flex flex-col">
      {/* 任务信息 */}
      <div className="p-4 border-b border-cyan-500/20">
        <h3 className="font-semibold text-white mb-2">{task.content}</h3>
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span>ID: {task.id}</span>
          <span>状态: {task.status}</span>
          <span>输出类型: {task.output_type ?? 'report'}</span>
        </div>
      </div>

      {/* 执行阶段 */}
      <div className="p-4 border-b border-cyan-500/20">
        <h4 className="text-sm font-semibold text-gray-300 mb-3">执行阶段</h4>
        <div className="space-y-2">
          {task.stages.map((stage, index) => (
            <StageItem key={index} stage={stage} index={index} />
          ))}
        </div>
      </div>

      {/* 输出产物 */}
      {task.artifacts && task.artifacts.length > 0 && (
        <div className="border-b border-cyan-500/20">
          <ArtifactPanel artifacts={task.artifacts} taskId={task.id} />
          {task.artifacts.length > 1 && (
            <div className="px-4 pb-4">
              <DownloadAllButton taskId={task.id} />
            </div>
          )}
        </div>
      )}

      {/* 执行日志 */}
      <div className="flex-1 overflow-y-auto p-4">
        <h4 className="text-sm font-semibold text-gray-300 mb-3">执行日志</h4>
        <div className="space-y-2">
          <AnimatePresence>
            {logs.map((log, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`
                  text-xs p-2 rounded-lg
                  ${log.level === 'error' ? 'bg-red-500/10 text-red-400' : ''}
                  ${log.level === 'success' ? 'bg-emerald-500/10 text-emerald-400' : ''}
                  ${log.level === 'info' ? 'bg-cyan-500/10 text-gray-300' : ''}
                  ${log.level === 'warning' ? 'bg-yellow-500/10 text-yellow-400' : ''}
                `}
              >
                <span className="text-gray-500 mr-2">
                  {new Date(log.timestamp).toLocaleTimeString('zh-CN')}
                </span>
                {log.message}
              </motion.div>
            ))}
          </AnimatePresence>
          
          {logs.length === 0 && (
            <p className="text-gray-500 text-xs">等待执行日志...</p>
          )}
        </div>
      </div>
    </div>
  )
}

function StageItem({ stage, index }: { stage: ExecutionStage; index: number }) {
  const statusColors: Record<string, string> = {
    pending: 'bg-gray-600',
    running: 'bg-cyan-500 animate-pulse',
    completed: 'bg-emerald-500',
    failed: 'bg-red-500',
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center justify-center w-6 h-6 rounded-full bg-[#0a0e17] border border-gray-600">
        <span className="text-xs text-gray-400">{index + 1}</span>
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm text-white">{stage.name}</span>
          <div className={`w-2 h-2 rounded-full ${statusColors[stage.status] || 'bg-gray-600'}`} />
        </div>
        {stage.details && (
          <p className="text-xs text-gray-500 mt-0.5">{stage.details}</p>
        )}
      </div>
    </div>
  )
}
