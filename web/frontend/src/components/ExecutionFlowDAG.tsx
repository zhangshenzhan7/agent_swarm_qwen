import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import type { SubTaskNode, ExecutionFlowGraph as FlowGraphType } from '../types'

interface Props {
  flow: FlowGraphType | null
  onStepClick: (step: SubTaskNode) => void
}

// 状态颜色
const statusColors: Record<string, { bg: string; border: string; text: string; fill: string }> = {
  pending:   { bg: '#1e293b', border: '#475569', text: '#94a3b8', fill: '#334155' },
  waiting:   { bg: '#422006', border: '#eab308', text: '#facc15', fill: '#854d0e' },
  blocked:   { bg: '#431407', border: '#f97316', text: '#fb923c', fill: '#9a3412' },
  running:   { bg: '#083344', border: '#06b6d4', text: '#22d3ee', fill: '#155e75' },
  completed: { bg: '#052e16', border: '#10b981', text: '#34d399', fill: '#166534' },
  failed:    { bg: '#450a0a', border: '#ef4444', text: '#f87171', fill: '#991b1b' },
  skipped:   { bg: '#1e293b', border: '#64748b', text: '#64748b', fill: '#334155' },
}

const agentIcons: Record<string, string> = {
  searcher: '🔍', analyst: '📊', fact_checker: '✅', writer: '✍️',
  translator: '🌐', coder: '💻', researcher: '🔬', summarizer: '📝', supervisor: '👔',
}

const statusIcons: Record<string, string> = {
  pending: '⏸️', waiting: '⏳', blocked: '🚫', running: '🔄',
  completed: '✅', failed: '❌', skipped: '⏭️',
}

// 节点尺寸
const NODE_W = 180
const NODE_H = 72
const GAP_X = 80
const GAP_Y = 24
const PADDING = 40

/**
 * 将步骤按依赖层级分组（拓扑分层），用于 LR 布局
 */
function computeLayers(steps: SubTaskNode[]): SubTaskNode[][] {
  const stepMap = new Map(steps.map(s => [s.step_id, s]))
  const layerOf = new Map<string, number>()

  function getLayer(id: string): number {
    if (layerOf.has(id)) return layerOf.get(id)!
    const step = stepMap.get(id)
    if (!step || step.dependencies.length === 0) {
      layerOf.set(id, 0)
      return 0
    }
    const maxDep = Math.max(
      ...step.dependencies
        .filter(d => stepMap.has(d))
        .map(d => getLayer(d))
    )
    const layer = (maxDep >= 0 ? maxDep : 0) + 1
    layerOf.set(id, layer)
    return layer
  }

  steps.forEach(s => getLayer(s.step_id))

  const layers: SubTaskNode[][] = []
  steps.forEach(s => {
    const l = layerOf.get(s.step_id) ?? 0
    if (!layers[l]) layers[l] = []
    layers[l].push(s)
  })

  return layers.filter(Boolean)
}

/**
 * 计算每个节点的 (x, y) 坐标
 */
function computePositions(layers: SubTaskNode[][]) {
  const positions = new Map<string, { x: number; y: number }>()
  const maxNodesInLayer = Math.max(...layers.map(l => l.length), 1)

  layers.forEach((layer, li) => {
    const x = PADDING + li * (NODE_W + GAP_X)
    const totalHeight = layer.length * NODE_H + (layer.length - 1) * GAP_Y
    const maxTotalHeight = maxNodesInLayer * NODE_H + (maxNodesInLayer - 1) * GAP_Y
    const offsetY = PADDING + (maxTotalHeight - totalHeight) / 2

    layer.forEach((step, si) => {
      const y = offsetY + si * (NODE_H + GAP_Y)
      positions.set(step.step_id, { x, y })
    })
  })

  return positions
}

export default function ExecutionFlowDAG({ flow, onStepClick }: Props) {
  const [hoveredStep, setHoveredStep] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [isPanning, setIsPanning] = useState(false)
  const [panStart, setPanStart] = useState({ x: 0, y: 0 })
  const [scrollStart, setScrollStart] = useState({ x: 0, y: 0 })

  // 拖拽平移
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.dag-node')) return
    setIsPanning(true)
    setPanStart({ x: e.clientX, y: e.clientY })
    setScrollStart({
      x: containerRef.current?.scrollLeft ?? 0,
      y: containerRef.current?.scrollTop ?? 0,
    })
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning || !containerRef.current) return
    containerRef.current.scrollLeft = scrollStart.x - (e.clientX - panStart.x)
    containerRef.current.scrollTop = scrollStart.y - (e.clientY - panStart.y)
  }, [isPanning, panStart, scrollStart])

  const handleMouseUp = useCallback(() => setIsPanning(false), [])

  useEffect(() => {
    const handleGlobalUp = () => setIsPanning(false)
    window.addEventListener('mouseup', handleGlobalUp)
    return () => window.removeEventListener('mouseup', handleGlobalUp)
  }, [])

  const { positions, steps, svgWidth, svgHeight } = useMemo(() => {
    if (!flow || Object.keys(flow.steps).length === 0) {
      return { positions: new Map(), steps: [], svgWidth: 0, svgHeight: 0 }
    }

    const orderedSteps = flow.execution_order
      .map(id => flow.steps[id])
      .filter(Boolean)
    const allSteps = orderedSteps.length > 0
      ? orderedSteps
      : Object.values(flow.steps).sort((a, b) => a.step_number - b.step_number)

    const ls = computeLayers(allSteps)
    const pos = computePositions(ls)

    const maxX = Math.max(...Array.from(pos.values()).map(p => p.x), 0)
    const maxY = Math.max(...Array.from(pos.values()).map(p => p.y), 0)

    return {
      positions: pos,
      steps: allSteps,
      svgWidth: maxX + NODE_W + PADDING * 2,
      svgHeight: maxY + NODE_H + PADDING * 2,
    }
  }, [flow])

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

  return (
    <div className="h-full flex flex-col">
      {/* 进度条 */}
      <div className="px-4 py-3 border-b border-cyan-500/20 shrink-0">
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

      {/* 图例 */}
      <div className="px-4 py-2 border-b border-cyan-500/10 flex flex-wrap gap-3 text-[10px] shrink-0">
        {['running', 'completed', 'pending', 'failed', 'skipped'].map(s => {
          const c = statusColors[s]
          return (
            <span key={s} className="flex items-center gap-1">
              <span
                className="inline-block w-3 h-3 rounded-sm border"
                style={{ backgroundColor: c.fill, borderColor: c.border }}
              />
              <span style={{ color: c.text }}>{statusIcons[s]} {s}</span>
            </span>
          )
        })}
      </div>

      {/* DAG 画布 */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        style={{ userSelect: isPanning ? 'none' : 'auto' }}
      >
        <svg
          width={Math.max(svgWidth, 600)}
          height={Math.max(svgHeight, 300)}
          className="select-none"
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 8 3, 0 6" fill="#475569" />
            </marker>
            <marker
              id="arrowhead-active"
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 8 3, 0 6" fill="#06b6d4" />
            </marker>
          </defs>

          {/* 依赖连线 */}
          {steps.map(step => {
            const to = positions.get(step.step_id)
            if (!to) return null
            return step.dependencies.map(depId => {
              const from = positions.get(depId)
              if (!from) return null

              const isHighlighted =
                hoveredStep === step.step_id || hoveredStep === depId
              const x1 = from.x + NODE_W
              const y1 = from.y + NODE_H / 2
              const x2 = to.x
              const y2 = to.y + NODE_H / 2
              const cx1 = x1 + GAP_X * 0.4
              const cx2 = x2 - GAP_X * 0.4

              return (
                <path
                  key={`${depId}->${step.step_id}`}
                  d={`M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`}
                  fill="none"
                  stroke={isHighlighted ? '#06b6d4' : '#334155'}
                  strokeWidth={isHighlighted ? 2 : 1.5}
                  strokeDasharray={step.status === 'pending' ? '4 4' : undefined}
                  markerEnd={isHighlighted ? 'url(#arrowhead-active)' : 'url(#arrowhead)'}
                  style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
                />
              )
            })
          })}

          {/* 节点 */}
          {steps.map(step => {
            const pos = positions.get(step.step_id)
            if (!pos) return null
            const c = statusColors[step.status] || statusColors.pending
            const isHovered = hoveredStep === step.step_id
            const icon = agentIcons[step.agent_type] || '🤖'

            return (
              <g
                key={step.step_id}
                className="dag-node"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredStep(step.step_id)}
                onMouseLeave={() => setHoveredStep(null)}
                onClick={() => onStepClick(step)}
              >
                {/* 发光效果 */}
                {(step.status === 'running' || isHovered) && (
                  <rect
                    x={pos.x - 3}
                    y={pos.y - 3}
                    width={NODE_W + 6}
                    height={NODE_H + 6}
                    rx={14}
                    fill="none"
                    stroke={c.border}
                    strokeWidth={1}
                    opacity={0.4}
                  >
                    {step.status === 'running' && (
                      <animate
                        attributeName="opacity"
                        values="0.2;0.6;0.2"
                        dur="2s"
                        repeatCount="indefinite"
                      />
                    )}
                  </rect>
                )}

                {/* 节点背景 */}
                <rect
                  x={pos.x}
                  y={pos.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={12}
                  fill={c.bg}
                  stroke={isHovered ? '#06b6d4' : c.border}
                  strokeWidth={isHovered ? 2 : 1.5}
                  style={{ transition: 'stroke 0.2s' }}
                />

                {/* 图标背景 */}
                <rect
                  x={pos.x + 8}
                  y={pos.y + (NODE_H - 32) / 2}
                  width={32}
                  height={32}
                  rx={8}
                  fill={c.fill}
                  opacity={0.6}
                />

                {/* Agent 图标 */}
                <text
                  x={pos.x + 24}
                  y={pos.y + NODE_H / 2 + 1}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={16}
                >
                  {icon}
                </text>

                {/* 步骤名称 */}
                <text
                  x={pos.x + 48}
                  y={pos.y + 22}
                  fill={c.text}
                  fontSize={12}
                  fontWeight={600}
                >
                  {truncate(`${step.step_number}. ${step.name}`, 14)}
                </text>

                {/* Agent 类型 */}
                <text
                  x={pos.x + 48}
                  y={pos.y + 40}
                  fill="#64748b"
                  fontSize={10}
                >
                  {step.agent_name || step.agent_type}
                </text>

                {/* 状态标签 */}
                <text
                  x={pos.x + 48}
                  y={pos.y + 56}
                  fill={c.text}
                  fontSize={9}
                >
                  {statusIcons[step.status]} {step.status}
                </text>

                {/* 运行中动画指示器 */}
                {step.status === 'running' && (
                  <circle
                    cx={pos.x + NODE_W - 12}
                    cy={pos.y + 12}
                    r={4}
                    fill="#22d3ee"
                  >
                    <animate
                      attributeName="r"
                      values="3;5;3"
                      dur="1.5s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values="1;0.4;1"
                      dur="1.5s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

function truncate(str: string, maxLen: number): string {
  return str.length > maxLen ? str.slice(0, maxLen - 1) + '…' : str
}
