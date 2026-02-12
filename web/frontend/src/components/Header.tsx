import { Activity, Cpu, Zap } from 'lucide-react'
import type { PlatformStats } from '../types'

interface HeaderProps {
  stats: PlatformStats | null
  isConnected: boolean
}

export function Header({ stats, isConnected }: HeaderProps) {
  return (
    <header className="glass border-b border-cyan-500/20 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-400 to-purple-500 flex items-center justify-center neon-glow">
              <Cpu className="w-7 h-7 text-white" />
            </div>
            <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
          </div>
          <div>
            <h1 className="font-cyber text-xl font-bold gradient-text">
              AI WORKFORCE
            </h1>
            <p className="text-xs text-gray-500">智能协作运行平台</p>
          </div>
        </div>

        {/* 状态指标 */}
        <div className="flex items-center gap-8">
          <StatCard
            icon={<Activity className="w-4 h-4" />}
            label="运行中任务"
            value={stats?.running_tasks ?? 0}
            color="cyber-green"
          />
          <StatCard
            icon={<Zap className="w-4 h-4" />}
            label="活跃员工"
            value={stats?.active_agents ?? 0}
            total={stats?.total_agents}
            color="cyber-blue"
          />
          <StatCard
            icon={<Activity className="w-4 h-4" />}
            label="成功率"
            value={`${stats?.success_rate?.toFixed(1) ?? 100}%`}
            color="cyber-purple"
          />
          
          {/* 连接状态 */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full glass">
            <div className={`status-dot ${isConnected ? 'running' : 'failed'}`} />
            <span className="text-xs text-gray-400">
              {isConnected ? '已连接' : '断开连接'}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}

interface StatCardProps {
  icon: React.ReactNode
  label: string
  value: number | string
  total?: number
  color: 'cyber-green' | 'cyber-blue' | 'cyber-purple'
}

function StatCard({ icon, label, value, total, color }: StatCardProps) {
  const colorClasses = {
    'cyber-green': 'bg-emerald-500/10 text-emerald-400',
    'cyber-blue': 'bg-cyan-500/10 text-cyan-400',
    'cyber-purple': 'bg-purple-500/10 text-purple-400',
  }
  
  return (
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-lg ${colorClasses[color]}`}>
        {icon}
      </div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="font-cyber text-lg font-semibold">
          {value}
          {total !== undefined && (
            <span className="text-gray-500 text-sm">/{total}</span>
          )}
        </p>
      </div>
    </div>
  )
}
