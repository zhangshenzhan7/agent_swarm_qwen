import { useState, useCallback, useEffect, useRef } from 'react'
import type { Agent, Task, LogEntry, WSMessage, SubTaskNode, ExecutionFlowGraph as FlowGraphType } from './types'
import ExecutionFlowGraph, { StepDetailModal } from './components/ExecutionFlowGraph'
import ExecutionFlowDAG from './components/ExecutionFlowDAG'
import { MeetingRoom } from './components/MeetingRoom'
import { SupervisorPanel } from './components/SupervisorPanel'
import { API_BASE, WS_BASE } from './config'

// 清理文本中的 THINKING 标签
function cleanThinkingTags(text: string): string {
  if (!text) return ''
  let result = text
  // 移除 [THINKING]...[/THINKING] 标签对及其内容
  for (let i = 0; i < 10; i++) {
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

// 简单的 Markdown 渲染组件
function MarkdownRenderer({ content }: { content: string | null | undefined }) {
  // 先清理 THINKING 标签
  const cleanedContent = cleanThinkingTags(content || '')
  
  // 简单的 Markdown 解析
  const renderMarkdown = (text: string) => {
    if (!text || typeof text !== 'string') {
      return [<p key="empty" className="text-slate-400">暂无内容</p>]
    }
    const lines = text.split('\n')
    const elements: JSX.Element[] = []
    let inCodeBlock = false
    let codeContent = ''
    // let codeLanguage = ''
    let tableRows: string[][] = []
    let inTable = false

    const flushTable = () => {
      if (tableRows.length > 0) {
        const headerRow = tableRows[0]
        // Skip separator row (|---|---|)
        const dataStartIdx = tableRows.length > 1 && tableRows[1].every(c => /^[-:]+$/.test(c.trim())) ? 2 : 1
        const dataRows = tableRows.slice(dataStartIdx)
        elements.push(
          <div key={`table-${elements.length}`} className="overflow-x-auto my-3">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-slate-600">
                  {headerRow.map((cell, ci) => (
                    <th key={ci} className="px-3 py-2 text-left text-cyan-400 font-semibold">{cell.trim()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, ri) => (
                  <tr key={ri} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-3 py-1.5 text-slate-300">{renderInlineMarkdown(cell.trim())}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
        tableRows = []
        inTable = false
      }
    }
    
    lines.forEach((line, i) => {
      // 代码块
      if (line.startsWith('```')) {
        if (inCodeBlock) {
          elements.push(
            <pre key={i} className="bg-slate-800/50 rounded-lg p-3 my-2 overflow-x-auto">
              <code className="text-sm text-emerald-300">{codeContent}</code>
            </pre>
          )
          codeContent = ''
          inCodeBlock = false
        } else {
          inCodeBlock = true
          // codeLanguage = line.slice(3)
        }
        return
      }
      
      if (inCodeBlock) {
        codeContent += line + '\n'
        return
      }

      // 表格行检测: | col1 | col2 |
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        const cells = line.trim().slice(1, -1).split('|')
        tableRows.push(cells)
        inTable = true
        return
      } else if (inTable) {
        flushTable()
      }
      
      // 标题
      if (line.startsWith('# ')) {
        elements.push(<h1 key={i} className="text-xl font-bold text-white mt-4 mb-2">{line.slice(2)}</h1>)
      } else if (line.startsWith('## ')) {
        elements.push(<h2 key={i} className="text-lg font-semibold text-cyan-400 mt-4 mb-2">{line.slice(3)}</h2>)
      } else if (line.startsWith('### ')) {
        elements.push(<h3 key={i} className="text-base font-semibold text-purple-400 mt-3 mb-1">{line.slice(4)}</h3>)
      }
      // 引用块
      else if (line.startsWith('> ')) {
        elements.push(
          <blockquote key={i} className="border-l-2 border-cyan-500/50 pl-3 my-2 text-slate-400 text-sm">
            {line.slice(2)}
          </blockquote>
        )
      }
      // 列表项
      else if (line.match(/^[-*] /)) {
        elements.push(
          <li key={i} className="text-slate-300 text-sm ml-4 my-1 list-disc">
            {renderInlineMarkdown(line.slice(2))}
          </li>
        )
      }
      // 数字列表
      else if (line.match(/^\d+\. /)) {
        const match = line.match(/^(\d+)\. (.*)/)
        if (match) {
          elements.push(
            <li key={i} className="text-slate-300 text-sm ml-4 my-1 list-decimal">
              {renderInlineMarkdown(match[2])}
            </li>
          )
        }
      }
      // 分隔线
      else if (line.match(/^---+$/)) {
        elements.push(<hr key={i} className="border-slate-700 my-4" />)
      }
      // 独立图片行: ![alt](url)
      else if (line.match(/^!\[[^\]]*\]\([^)]+\)$/)) {
        const imgMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/)
        if (imgMatch) {
          const [, alt, src] = imgMatch
          // 检测是否为视频 URL
          if (src.match(/\.(mp4|webm|mov)(\?|$)/i)) {
            elements.push(
              <div key={i} className="my-3">
                <video controls className="max-w-full rounded-lg border border-slate-700" preload="metadata">
                  <source src={src} type="video/mp4" />
                  <a href={src} target="_blank" rel="noopener noreferrer" className="text-cyan-400">{alt || '下载视频'}</a>
                </video>
              </div>
            )
          } else {
            elements.push(
              <div key={i} className="my-3">
                <img src={src} alt={alt} className="max-w-full rounded-lg border border-slate-700" loading="lazy" />
                {alt && <p className="text-xs text-slate-500 mt-1">{alt}</p>}
              </div>
            )
          }
        }
      }
      // 独立视频 URL 行（http(s)://...mp4 等）
      else if (line.trim().match(/^https?:\/\/[^\s]+\.(mp4|webm|mov)(\?[^\s]*)?$/i)) {
        const videoUrl = line.trim()
        elements.push(
          <div key={i} className="my-3">
            <video controls className="max-w-full rounded-lg border border-slate-700" preload="metadata">
              <source src={videoUrl} type="video/mp4" />
            </video>
            <a href={videoUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-cyan-400 mt-1 block">下载视频</a>
          </div>
        )
      }
      // 空行
      else if (line.trim() === '') {
        elements.push(<div key={i} className="h-2" />)
      }
      // 普通段落
      else {
        elements.push(
          <p key={i} className="text-slate-300 text-sm my-1 leading-relaxed">
            {renderInlineMarkdown(line)}
          </p>
        )
      }
    })

    // Flush any remaining table
    flushTable()
    
    return elements
  }
  
  // 渲染行内 Markdown（加粗、斜体、代码、链接、图片等）
  const renderInlineMarkdown = (text: string) => {
    // 处理加粗、行内代码、图片、链接、裸 URL
    const parts = text.split(/(!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|https?:\/\/[^\s<]+)/g)
    return parts.map((part, i) => {
      // 图片: ![alt](url)
      const imgMatch = part.match(/^!\[([^\]]*)\]\(([^)]+)\)$/)
      if (imgMatch) {
        const [, alt, src] = imgMatch
        return <img key={i} src={src} alt={alt} className="max-w-full rounded-lg my-2 border border-slate-700 inline-block" loading="lazy" />
      }
      // 链接: [text](url)
      const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      if (linkMatch) {
        const [, linkText, href] = linkMatch
        return <a key={i} href={href} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-300 underline">{linkText}</a>
      }
      // 裸 URL
      if (part.match(/^https?:\/\/[^\s<]+$/)) {
        return <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-300 underline break-all">{part}</a>
      }
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={i} className="bg-slate-700/50 px-1 rounded text-cyan-300 text-xs">{part.slice(1, -1)}</code>
      }
      return part
    })
  }
  
  return <div className="markdown-content">{renderMarkdown(cleanedContent)}</div>
}

// 格式化流式输出内容，美化 thinking 过程显示
function FormattedStreamContent({ content }: { content: string }) {
  // 按阶段分割内容，每个阶段有独立的 thinking 块
  const parseContentByPhase = (text: string) => {
    // 先按 [NEW_PHASE] 分割成多个阶段
    const phases = text.split('[NEW_PHASE]').filter(p => p.trim())
    
    return phases.map(phaseContent => {
      let thinkingContent = ''
      let normalContent = ''
      let remaining = phaseContent
      
      while (remaining.length > 0) {
        const thinkingStart = remaining.indexOf('[THINKING]')
        
        if (thinkingStart === -1) {
          normalContent += remaining
          break
        }
        
        if (thinkingStart > 0) {
          normalContent += remaining.slice(0, thinkingStart)
        }
        
        const thinkingEnd = remaining.indexOf('[/THINKING]', thinkingStart)
        
        if (thinkingEnd === -1) {
          // 未闭合的 thinking 块（正在流式输出中）
          thinkingContent += remaining.slice(thinkingStart + 10)
          break
        }
        
        // 拼接 thinking 内容，不做 trim，保留原始换行
        thinkingContent += remaining.slice(thinkingStart + 10, thinkingEnd)
        remaining = remaining.slice(thinkingEnd + 11)
      }
      
      return { 
        thinkingContent: thinkingContent.replace(/^\n+/, '').replace(/\n+$/, ''), 
        normalContent: normalContent.trim() 
      }
    })
  }
  
  const phases = parseContentByPhase(content)
  
  return (
    <div className="space-y-3">
      {phases.map((phase, i) => (
        <div key={i} className="space-y-2">
          {/* 先显示深度思考内容 */}
          {phase.thinkingContent && (
            <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-purple-400 text-xs font-medium">🧠 深度思考</span>
                <div className="flex-1 h-px bg-purple-500/30" />
              </div>
              <pre className="text-xs text-purple-300/80 whitespace-pre-wrap font-mono leading-relaxed max-h-32 overflow-auto">{phase.thinkingContent}</pre>
            </div>
          )}
          
          {/* 再显示输出结果 */}
          {phase.normalContent && (
            <pre className="text-xs text-cyan-300 whitespace-pre-wrap font-mono">{phase.normalContent}</pre>
          )}
        </div>
      ))}
    </div>
  )
}

function useWS(url: string, onMsg: (msg: WSMessage) => void) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const onMsgRef = useRef(onMsg)
  const reconnectRef = useRef<number>()
  const heartbeatRef = useRef<number>()
  onMsgRef.current = onMsg

  useEffect(() => {
    let mounted = true

    const connect = () => {
      if (!mounted) return
      try {
        if (wsRef.current) wsRef.current.close()
        const ws = new WebSocket(url)
        ws.onopen = () => {
          console.log('WebSocket connected')
          if (mounted) setConnected(true)
        }
        ws.onclose = () => {
          console.log('WebSocket disconnected, reconnecting in 3s...')
          if (mounted) {
            setConnected(false)
            reconnectRef.current = window.setTimeout(connect, 3000)
          }
        }
        ws.onerror = (e) => console.error('WebSocket error:', e)
        ws.onmessage = (e) => { try { onMsgRef.current(JSON.parse(e.data)) } catch {} }
        wsRef.current = ws
      } catch (e) {
        console.error('WebSocket connect failed:', e)
        if (mounted) reconnectRef.current = window.setTimeout(connect, 3000)
      }
    }

    connect()

    heartbeatRef.current = window.setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      mounted = false
      clearTimeout(reconnectRef.current)
      clearInterval(heartbeatRef.current)
      wsRef.current?.close()
    }
  }, [url])
  return connected
}

// 文件类型图标映射
const FILE_TYPE_ICONS: Record<string, string> = {
  'image': '🖼️',
  'video': '🎬',
  'audio': '🎵',
  'application/pdf': '📄',
  'text': '📝',
  'application/json': '📋',
  'default': '📎'
}

function getFileIcon(type: string): string {
  if (type.startsWith('image/')) return FILE_TYPE_ICONS['image']
  if (type.startsWith('video/')) return FILE_TYPE_ICONS['video']
  if (type.startsWith('audio/')) return FILE_TYPE_ICONS['audio']
  if (type.startsWith('text/')) return FILE_TYPE_ICONS['text']
  return FILE_TYPE_ICONS[type] || FILE_TYPE_ICONS['default']
}

interface UploadedFile {
  id: string
  name: string
  type: string
  size: number
  url: string
  base64?: string
}

export default function App() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [logs, setLogs] = useState<Record<string, LogEntry[]>>({})
  const [agentLogs, setAgentLogs] = useState<Record<string, LogEntry[]>>({})
  const [agentStreams, setAgentStreams] = useState<Record<string, string>>({})
  // 按 task_id 索引的 agent 日志和流式输出
  const [taskAgentLogs, setTaskAgentLogs] = useState<Record<string, Record<string, LogEntry[]>>>({})
  const [taskAgentStreams, setTaskAgentStreams] = useState<Record<string, Record<string, string>>>({})
  const [input, setInput] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false)
  const [settingsMsg, setSettingsMsg] = useState('')
  const [executionMode, setExecutionMode] = useState<'scheduler' | 'team'>('scheduler')
  const [sandboxAccountId, setSandboxAccountId] = useState('')
  const [sandboxAccessKeyId, setSandboxAccessKeyId] = useState('')
  const [sandboxAccessKeySecret, setSandboxAccessKeySecret] = useState('')
  const [sandboxAccessKeyConfigured, setSandboxAccessKeyConfigured] = useState(false)
  const [executionFlow, setExecutionFlow] = useState<FlowGraphType | null>(null)
  const [selectedStep, setSelectedStep] = useState<SubTaskNode | null>(null)
  const [showFlowView, setShowFlowView] = useState<'stages' | 'list' | 'dag'>('stages')
  const [activeTab, setActiveTab] = useState<'workspace' | 'meeting'>('workspace')
  
  // 文件上传相关状态
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [recommendedRoles, setRecommendedRoles] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const selectedTask = tasks.find(t => t.id === selectedId) || null
  const selectedAgent = agents.find(a => a.id === selectedAgentId) || null

  // 清除主管面板数据（思考和日志）
  const clearSupervisorData = useCallback(() => {
    // 清除所有主管相关的流式输出和日志
    const supervisorIds = Object.keys(agentStreams).filter(id => 
      id === 'supervisor' || id.startsWith('agent_supervisor_')
    )
    
    // 清除流式输出
    setAgentStreams(prev => {
      const newStreams = { ...prev }
      supervisorIds.forEach(id => {
        newStreams[id] = ''
      })
      // 同时清除所有 agent 的流式输出
      Object.keys(newStreams).forEach(id => {
        newStreams[id] = ''
      })
      return newStreams
    })
    
    // 清除日志
    setAgentLogs(prev => {
      const newLogs = { ...prev }
      supervisorIds.forEach(id => {
        newLogs[id] = []
      })
      return newLogs
    })
  }, [agentStreams])

  // 检查 API Key 配置状态（从 Cookie 恢复）
  useEffect(() => {
    fetch(`${API_BASE}/api/config`, {
      credentials: 'include'  // 发送 Cookie
    })
      .then(r => r.json())
      .then(d => {
        setApiKeyConfigured(d.api_key_configured)
        setExecutionMode(d.execution_mode || 'scheduler')
        if (d.sandbox_account_id) setSandboxAccountId(d.sandbox_account_id)
        setSandboxAccessKeyConfigured(!!d.sandbox_access_key_configured)
        if (!d.api_key_configured) setShowSettings(true)
      })
      .catch(() => {})
  }, [])

  // 获取任务执行流程
  const fetchExecutionFlow = useCallback(async (taskId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/tasks/${taskId}/flow`)
      if (res.ok) {
        const flow = await res.json()
        setExecutionFlow(flow)
      }
    } catch (e) {
      console.error('Failed to fetch execution flow:', e)
    }
  }, [])

  // 当选中任务变化时，获取执行流程
  useEffect(() => {
    if (selectedId) {
      fetchExecutionFlow(selectedId)
      // 定期刷新执行流程（任务执行中时）
      const task = tasks.find(t => t.id === selectedId)
      if (task && ['pending', 'executing', 'analyzing', 'decomposing', 'aggregating'].includes(task.status)) {
        const interval = setInterval(() => fetchExecutionFlow(selectedId), 1000)  // 加快刷新频率
        return () => clearInterval(interval)
      }
    } else {
      setExecutionFlow(null)
    }
  }, [selectedId, tasks, fetchExecutionFlow])

  const saveApiKey = async () => {
    if (!apiKey.trim()) return
    const res = await fetch(`${API_BASE}/api/config/apikey`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',  // 允许发送和接收 Cookie
      body: JSON.stringify({ api_key: apiKey })
    })
    const data = await res.json()
    setSettingsMsg(data.message)
    if (data.success) {
      setApiKeyConfigured(true)
      setTimeout(() => setShowSettings(false), 1500)
    }
  }

  const handleLogout = async () => {
    await fetch(`${API_BASE}/api/config/logout`, {
      method: 'POST',
      credentials: 'include'
    })
    setApiKeyConfigured(false)
    setApiKey('')
    setSettingsMsg('已退出登录')
  }

  const switchExecutionMode = async (mode: 'scheduler' | 'team') => {
    if (mode === executionMode) return
    try {
      const res = await fetch(`${API_BASE}/api/config/execution-mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      })
      const data = await res.json()
      if (data.success) {
        setExecutionMode(mode)
        setSettingsMsg(data.message)
        setTimeout(() => setSettingsMsg(''), 3000)
      } else {
        setSettingsMsg(data.message)
      }
    } catch {
      setSettingsMsg('切换执行模式失败')
    }
  }

  const saveSandboxConfig = async () => {
    try {
      const body: any = {
        sandbox_account_id: sandboxAccountId.trim() || null,
      }
      // 仅在用户填写了 AK/SK 时发送（避免覆盖已有配置）
      if (sandboxAccessKeyId.trim()) {
        body.sandbox_access_key_id = sandboxAccessKeyId.trim()
      }
      if (sandboxAccessKeySecret.trim()) {
        body.sandbox_access_key_secret = sandboxAccessKeySecret.trim()
      }
      const res = await fetch(`${API_BASE}/api/config/sandbox`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      const data = await res.json()
      setSettingsMsg(data.message)
      if (data.success) {
        // 清空密钥输入框，刷新配置状态
        setSandboxAccessKeyId('')
        setSandboxAccessKeySecret('')
        // 重新获取配置以更新 configured 状态
        const configRes = await fetch(`${API_BASE}/api/config`, { credentials: 'include' })
        const configData = await configRes.json()
        setSandboxAccessKeyConfigured(!!configData.sandbox_access_key_configured)
      }
      setTimeout(() => setSettingsMsg(''), 3000)
    } catch {
      setSettingsMsg('沙箱配置保存失败')
    }
  }

  const handleWS = useCallback((msg: WSMessage) => {
    if (msg.type === 'init') {
      const d = msg.data as { agents: Agent[]; tasks: Task[] }
      setAgents(d.agents); setTasks(d.tasks)
    } else if (['task_created', 'task_updated', 'task_completed'].includes(msg.type)) {
      const t = msg.data as Task
      setTasks(prev => {
        const idx = prev.findIndex(x => x.id === t.id)
        return idx >= 0 ? [...prev.slice(0, idx), t, ...prev.slice(idx + 1)] : [t, ...prev]
      })
      // 如果是当前选中的任务，刷新执行流程
      if (t.id === selectedId) {
        fetchExecutionFlow(t.id)
      }
    } else if (msg.type === 'agent_updated') {
      setAgents(prev => {
        const agent = msg.data as Agent
        const idx = prev.findIndex(x => x.id === agent.id)
        if (idx >= 0) {
          return [...prev.slice(0, idx), agent, ...prev.slice(idx + 1)]
        }
        // 如果是新 agent，添加到列表
        return [...prev, agent]
      })
    } else if (msg.type === 'agent_created') {
      // 动态创建的 agent 实例
      const agent = msg.data as Agent
      setAgents(prev => {
        if (prev.find(x => x.id === agent.id)) return prev
        return [...prev, agent]
      })
    } else if (msg.type === 'agent_removed') {
      // 移除动态创建的 agent 实例
      const d = msg.data as { id: string }
      setAgents(prev => prev.filter(x => x.id !== d.id))
    } else if (msg.type === 'task_log') {
      const d = msg.data as { task_id: string; log: LogEntry }
      setLogs(prev => ({ ...prev, [d.task_id]: [...(prev[d.task_id] || []), d.log] }))
    } else if (msg.type === 'agent_log') {
      const d = msg.data as { agent_id: string; task_id?: string; log: LogEntry }
      setAgentLogs(prev => ({ ...prev, [d.agent_id]: [...(prev[d.agent_id] || []).slice(-99), d.log] }))
      // 同时按 task_id 存储
      if (d.task_id) {
        setTaskAgentLogs(prev => {
          const taskLogs = prev[d.task_id] || {}
          return { ...prev, [d.task_id]: { ...taskLogs, [d.agent_id]: [...(taskLogs[d.agent_id] || []).slice(-99), d.log] } }
        })
      }
    } else if (msg.type === 'agent_stream') {
      const d = msg.data as { agent_id: string; task_id?: string; content: string; full_content: string }
      setAgentStreams(prev => ({ ...prev, [d.agent_id]: d.full_content }))
      // 同时按 task_id 存储
      if (d.task_id) {
        setTaskAgentStreams(prev => {
          const taskStreams = prev[d.task_id] || {}
          return { ...prev, [d.task_id]: { ...taskStreams, [d.agent_id]: d.full_content } }
        })
      }
    } else if (msg.type === 'agent_stream_clear') {
      const d = msg.data as { agent_id: string; task_id?: string }
      setAgentStreams(prev => ({ ...prev, [d.agent_id]: '' }))
      if (d.task_id) {
        setTaskAgentStreams(prev => {
          const taskStreams = prev[d.task_id] || {}
          return { ...prev, [d.task_id]: { ...taskStreams, [d.agent_id]: '' } }
        })
      }
    } else if (msg.type === 'execution_flow_updated') {
      // 执行流程更新
      const d = msg.data as { task_id: string; flow: FlowGraphType }
      if (d.task_id === selectedId) {
        setExecutionFlow(d.flow)
      }
    } else if (msg.type === 'step_status_changed') {
      // 步骤状态变化（包含完整步骤数据）
      const d = msg.data as { task_id: string; step_id: string; status: string; output_data?: string; error?: string; agent_id?: string; agent_name?: string; started_at?: string; completed_at?: string; logs?: LogEntry[] }
      if (d.task_id === selectedId && executionFlow) {
        setExecutionFlow(prev => {
          if (!prev) return prev
          const newSteps = { ...prev.steps }
          if (newSteps[d.step_id]) {
            newSteps[d.step_id] = {
              ...newSteps[d.step_id],
              status: d.status as any,
              output_data: d.output_data ?? newSteps[d.step_id].output_data,
              error: d.error ?? newSteps[d.step_id].error,
              agent_id: d.agent_id ?? newSteps[d.step_id].agent_id,
              agent_name: d.agent_name ?? newSteps[d.step_id].agent_name,
              started_at: d.started_at ?? newSteps[d.step_id].started_at,
              completed_at: d.completed_at ?? newSteps[d.step_id].completed_at,
              logs: d.logs || newSteps[d.step_id].logs,
            }
          }
          return { ...prev, steps: newSteps }
        })
      }
    } else if (msg.type === 'task_progress') {
      // 任务进度更新（轻量级，不含步骤详情）
      const d = msg.data as { task_id: string; progress: any; status?: string }
      if (d.task_id === selectedId && executionFlow) {
        setExecutionFlow(prev => prev ? { ...prev, progress: d.progress } : prev)
      }
      if (d.status) {
        setTasks(prev => prev.map(t => t.id === d.task_id ? { ...t, status: d.status! } : t))
      }
    }
  }, [selectedId, fetchExecutionFlow, executionFlow])

  const connected = useWS(`${WS_BASE}/ws`, handleWS)

  // 文件上传处理
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    
    setIsUploading(true)
    const formData = new FormData()
    
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }
    
    try {
      const res = await fetch(`${API_BASE}/api/upload/multiple`, {
        method: 'POST',
        body: formData
      })
      const data = await res.json()
      
      if (data.results) {
        const newFiles = data.results
          .filter((r: any) => r.success)
          .map((r: any) => r.file)
        setUploadedFiles(prev => [...prev, ...newFiles])
        setRecommendedRoles(data.all_recommended_roles || [])
      }
    } catch (err) {
      console.error('Upload failed:', err)
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }
  
  const removeFile = (fileId: string) => {
    setUploadedFiles(prev => prev.filter(f => f.id !== fileId))
  }
  
  const clearFiles = () => {
    setUploadedFiles([])
    setRecommendedRoles([])
  }

  const createTask = async () => {
    if (!input.trim() && uploadedFiles.length === 0) return
    
    // 根据是否有文件选择不同的API
    const hasFiles = uploadedFiles.length > 0
    const endpoint = hasFiles ? `${API_BASE}/api/tasks/with-files` : `${API_BASE}/api/tasks`
    
    const body = hasFiles ? {
      content: input || '请分析以下文件',
      output_type: 'auto',
      files: uploadedFiles.map(f => ({
        id: f.id,
        name: f.name,
        type: f.type,
        size: f.size,
        url: f.url,
        base64: f.base64
      }))
    } : {
      content: input,
      output_type: 'auto',
    }
    
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    const task = await res.json()
    setSelectedId(task.id)
    setInput('')
    clearFiles()
  }

  const deleteTask = async (id: string) => {
    await fetch(`${API_BASE}/api/tasks/${id}`, { method: 'DELETE' })
    setTasks(prev => prev.filter(t => t.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  const runningAgents = agents.filter(a => a.status === 'running')

  return (
    <div className="min-h-screen bg-[#060912] text-slate-200 font-sans">
      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#0a0e17] border border-cyan-500/30 rounded-2xl p-6 w-[460px] max-h-[85vh] overflow-y-auto shadow-2xl">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold">⚙️ 设置</h2>
              <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">DashScope API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="sk-xxxxxxxxxxxxxxxx"
                  className="w-full px-4 py-3 rounded-xl bg-[#060912] border border-cyan-500/30 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400"
                />
                <p className="text-xs text-slate-500 mt-2">
                  从 <a href="https://dashscope.console.aliyun.com/" target="_blank" className="text-cyan-400 hover:underline">阿里云 DashScope</a> 获取 API Key
                </p>
              </div>
              
              <div className={`flex items-center gap-2 text-sm ${apiKeyConfigured ? 'text-emerald-400' : 'text-yellow-400'}`}>
                <span>{apiKeyConfigured ? '✅' : '⚠️'}</span>
                <span>{apiKeyConfigured ? 'API Key 已配置' : '请配置 API Key 以启用任务执行'}</span>
              </div>
              
              {/* 执行模式切换 */}
              <div className="border-t border-cyan-500/20 pt-4">
                <label className="block text-sm text-slate-400 mb-3">执行模式</label>
                <div className="flex items-center gap-2 bg-[#060912] rounded-xl p-1">
                  <button
                    onClick={() => switchExecutionMode('scheduler')}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                      executionMode === 'scheduler'
                        ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                        : 'text-slate-400 hover:text-slate-300 hover:bg-slate-800/50'
                    }`}
                  >
                    ⚡ 调度器模式
                  </button>
                  <button
                    onClick={() => switchExecutionMode('team')}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                      executionMode === 'team'
                        ? 'bg-purple-500/20 text-purple-400 border border-purple-500/50'
                        : 'text-slate-400 hover:text-slate-300 hover:bg-slate-800/50'
                    }`}
                  >
                    🌊 团队模式
                  </button>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  {executionMode === 'scheduler' 
                    ? '静态分层并行调度（默认）'
                    : '基于依赖关系的事件驱动波次执行'}
                </p>
              </div>
              
              {/* 沙箱代码解释器配置 */}
              <div className="border-t border-cyan-500/20 pt-4">
                <label className="block text-sm text-slate-400 mb-3">🔧 沙箱代码解释器（非 Qwen 模型）</label>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">阿里云主账号 ID</label>
                    <input
                      type="text"
                      value={sandboxAccountId}
                      onChange={e => setSandboxAccountId(e.target.value)}
                      placeholder="例如: 1708041401021944"
                      className="w-full px-3 py-2 rounded-lg bg-[#060912] border border-cyan-500/20 text-white placeholder-slate-600 text-sm focus:outline-none focus:border-cyan-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">AccessKey ID</label>
                    <input
                      type="text"
                      value={sandboxAccessKeyId}
                      onChange={e => setSandboxAccessKeyId(e.target.value)}
                      placeholder={sandboxAccessKeyConfigured ? '已配置（留空保持不变）' : 'LTAI5t...'}
                      className="w-full px-3 py-2 rounded-lg bg-[#060912] border border-cyan-500/20 text-white placeholder-slate-600 text-sm focus:outline-none focus:border-cyan-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">AccessKey Secret</label>
                    <input
                      type="password"
                      value={sandboxAccessKeySecret}
                      onChange={e => setSandboxAccessKeySecret(e.target.value)}
                      placeholder={sandboxAccessKeyConfigured ? '已配置（留空保持不变）' : '输入 AccessKey Secret'}
                      className="w-full px-3 py-2 rounded-lg bg-[#060912] border border-cyan-500/20 text-white placeholder-slate-600 text-sm focus:outline-none focus:border-cyan-400"
                    />
                  </div>
                  {sandboxAccessKeyConfigured && (
                    <div className="flex items-center gap-2 text-xs text-emerald-400">
                      <span>✅</span><span>AK/SK 已配置（支持自动创建沙箱模板）</span>
                    </div>
                  )}
                  <button
                    onClick={saveSandboxConfig}
                    className="w-full py-2 rounded-lg border border-cyan-500/30 text-cyan-400 text-sm hover:bg-cyan-500/10 transition-all"
                  >
                    保存沙箱配置
                  </button>
                  <p className="text-xs text-slate-500">
                    当 coder/analyst 使用非 Qwen 模型时，通过阿里云 AgentRun Sandbox 执行代码。
                    AK/SK 用于自动创建沙箱模板，也可通过环境变量配置。
                  </p>
                </div>
              </div>

              {settingsMsg && (
                <div className={`p-3 rounded-lg text-sm ${settingsMsg.includes('失败') ? 'bg-red-500/10 text-red-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
                  {settingsMsg}
                </div>
              )}
              
              <button
                onClick={saveApiKey}
                disabled={!apiKey.trim()}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-purple-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-lg hover:shadow-cyan-500/20 transition-all"
              >
                保存设置
              </button>
              
              {apiKeyConfigured && (
                <button
                  onClick={handleLogout}
                  className="w-full py-3 rounded-xl border border-red-500/50 text-red-400 hover:bg-red-500/10 transition-all"
                >
                  🚪 退出登录
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Step Detail Modal */}
      {selectedStep && (
        <StepDetailModal step={selectedStep} onClose={() => setSelectedStep(null)} />
      )}

      {/* Agent Detail Modal */}
      {selectedAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setSelectedAgentId(null)}>
          <div className="bg-[#0a0e17] border border-cyan-500/30 rounded-2xl w-[600px] max-h-[80vh] shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="p-5 border-b border-cyan-500/20 flex items-center gap-4">
              <div className={`w-16 h-16 rounded-xl flex items-center justify-center text-3xl ${selectedAgent.status === 'running' ? 'bg-emerald-500/20 animate-pulse' : 'bg-slate-700/50'}`}>
                {selectedAgent.avatar}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-semibold">{selectedAgent.name}</h2>
                  <div className={`px-2 py-1 rounded-full text-xs ${selectedAgent.status === 'running' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700 text-slate-400'}`}>
                    {selectedAgent.status === 'running' ? '工作中' : '待命'}
                  </div>
                </div>
                <p className="text-sm text-slate-400 mt-1">{selectedAgent.description}</p>
              </div>
              <button onClick={() => setSelectedAgentId(null)} className="text-slate-400 hover:text-white text-xl">✕</button>
            </div>
            
            {/* Current Task */}
            {selectedAgent.current_task && (
              <div className="px-5 py-3 bg-emerald-500/5 border-b border-emerald-500/20">
                <p className="text-xs text-slate-500 mb-1">当前任务</p>
                <p className="text-sm text-emerald-400">⚡ {selectedAgent.current_task}</p>
              </div>
            )}
            
            {/* Streaming Output */}
            {agentStreams[selectedAgent.id] && (
              <div className="px-5 py-3 bg-cyan-500/5 border-b border-cyan-500/20">
                <p className="text-xs text-slate-500 mb-2">实时输出</p>
                <div className="bg-[#060912] rounded-lg p-3 max-h-48 overflow-auto">
                  <FormattedStreamContent content={agentStreams[selectedAgent.id]} />
                </div>
              </div>
            )}
            
            {/* Logs */}
            <div className="flex-1 overflow-auto p-5">
              <h3 className="text-sm text-slate-400 mb-3">执行日志</h3>
              <div className="space-y-2">
                {(agentLogs[selectedAgent.id] || []).slice(-50).map((log, i) => (
                  <div key={i} className={`text-xs p-2 rounded-lg ${log.level === 'error' ? 'bg-red-500/10 text-red-400' : log.level === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-800/50 text-slate-300'}`}>
                    <span className="text-slate-500 mr-2">{new Date(log.timestamp).toLocaleTimeString()}</span>
                    <span className="whitespace-pre-wrap">{log.message}</span>
                  </div>
                ))}
                {(agentLogs[selectedAgent.id] || []).length === 0 && (
                  <p className="text-slate-500 text-xs text-center py-8">暂无执行日志</p>
                )}
              </div>
            </div>
            
            {/* Stats */}
            {selectedAgent.stats && (
              <div className="p-5 border-t border-cyan-500/20 bg-[#060912]/50">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-xs text-slate-500">完成任务</p>
                    <p className="text-lg font-semibold text-cyan-400">{selectedAgent.stats.tasks_completed}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">成功率</p>
                    <p className="text-lg font-semibold text-emerald-400">{selectedAgent.stats.success_rate || 100}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">工具数</p>
                    <p className="text-lg font-semibold text-purple-400">{selectedAgent.tools.length}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/5 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 flex flex-col h-screen">
        {/* Header */}
        <header className="bg-[#0a0e17]/80 backdrop-blur border-b border-cyan-500/20 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="relative">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-400 to-purple-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
                  <span className="text-2xl">🤖</span>
                </div>
                <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <div>
                <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
                  AI WORKFORCE
                </h1>
                <p className="text-xs text-slate-500">智能协作运行平台</p>
              </div>
            </div>
            
            {/* Tab 切换 */}
            <div className="flex items-center gap-2 px-2 py-1 rounded-xl bg-[#060912] border border-cyan-500/20">
              <button
                onClick={() => setActiveTab('workspace')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === 'workspace'
                    ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-white border border-cyan-500/30'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                }`}
              >
                <span className="mr-2">💼</span>工作台
              </button>
              <button
                onClick={() => setActiveTab('meeting')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === 'meeting'
                    ? 'bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-white border border-purple-500/30'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                }`}
              >
                <span className="mr-2">🏢</span>会议室
              </button>
            </div>

            <div className="flex items-center gap-8">
              <StatCard label="运行中任务" value={tasks.filter(t => ['pending','executing','analyzing','decomposing','aggregating'].includes(t.status)).length} icon="🚀" color="cyan" />
              <StatCard label="活跃员工" value={`${runningAgents.length}/${agents.length}`} icon="👥" color="emerald" />
              <StatCard label="已完成" value={tasks.filter(t => t.status === 'completed').length} icon="✅" color="purple" />
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${connected ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-red-500/10 border-red-500/30'} border`}>
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
                <span className="text-xs text-slate-400">{connected ? '🟢 在线' : '🔴 离线'}</span>
              </div>
              <button onClick={() => setShowSettings(true)} className="p-2 rounded-lg hover:bg-slate-700/50 transition-colors" title="设置">
                ⚙️
              </button>
            </div>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1 flex overflow-hidden">
          {activeTab === 'meeting' ? (
            /* 会议室视图 */
            <MeetingRoom agents={agents} onAgentClick={setSelectedAgentId} agentStreams={agentStreams} />
          ) : (
            /* 工作台视图 */
            <>
          {/* Left: Task Input + List */}
          <aside className="w-80 border-r border-cyan-500/20 bg-[#0a0e17]/50 flex flex-col">
            <div className="p-4 border-b border-cyan-500/10">
              {/* 文件预览区域 */}
              {uploadedFiles.length > 0 && (
                <div className="mb-3 p-2 bg-slate-800/50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-400">已选择 {uploadedFiles.length} 个文件</span>
                    <button onClick={clearFiles} className="text-xs text-red-400 hover:text-red-300">清空</button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {uploadedFiles.map(file => (
                      <div key={file.id} className="flex items-center gap-1 px-2 py-1 bg-slate-700/50 rounded-lg text-xs">
                        <span>{getFileIcon(file.type)}</span>
                        <span className="max-w-[100px] truncate text-slate-300">{file.name}</span>
                        <button onClick={() => removeFile(file.id)} className="text-slate-500 hover:text-red-400 ml-1">×</button>
                      </div>
                    ))}
                  </div>
                  {recommendedRoles.length > 0 && (
                    <div className="mt-2 text-xs text-slate-500">
                      推荐角色: {recommendedRoles.slice(0, 3).join(', ')}
                    </div>
                  )}
                </div>
              )}
              
              {/* 输入区域 */}
              <div className="space-y-3">
                <div className="flex gap-2">
                  <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && createTask()}
                    placeholder={uploadedFiles.length > 0 ? "描述你想对文件做什么..." : "输入任务描述，让 AI 员工帮你完成..."}
                    className="flex-1 px-4 py-3 rounded-xl bg-[#0a0e17] border border-cyan-500/30 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 text-sm" />
                
                {/* 文件上传按钮 */}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.json,.py,.js,.ts,.java,.go,.rs,.html,.css"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                  className={`px-3 rounded-xl border transition-all ${isUploading ? 'border-slate-600 text-slate-500' : 'border-purple-500/30 text-purple-400 hover:bg-purple-500/10 hover:border-purple-500/50'}`}
                  title="上传文件"
                >
                  {isUploading ? '⏳' : '📎'}
                </button>
                
                {/* 发送按钮 */}
                <button onClick={createTask} className="px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-purple-500 text-white font-medium hover:shadow-lg hover:shadow-cyan-500/20 transition-all">
                  <span>📤</span>
                </button>
              </div>
              
              {/* 快捷操作提示 */}
              <div className="mt-2 flex gap-2 text-xs text-slate-500">
                <span>支持: 图片 📷 文档 📄 代码 💻 视频 🎬</span>
              </div>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-3 space-y-2">
              {tasks.map(task => (
                <div key={task.id} onClick={() => setSelectedId(task.id)}
                  className={`p-3 rounded-xl cursor-pointer transition-all border ${selectedId === task.id ? 'bg-cyan-500/10 border-cyan-500/50 ring-1 ring-cyan-500/30' : 'bg-[#0a0e17]/60 border-cyan-500/10 hover:border-cyan-500/30'}`}>
                  <div className="flex items-start gap-2">
                    <TaskStatusIcon status={task.status} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate">{task.content}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <p className="text-xs text-slate-500">{new Date(task.created_at).toLocaleString('zh-CN')}</p>
                        {task.files && task.files.length > 0 && (
                          <span className="text-xs text-purple-400">📎 {task.files.length}</span>
                        )}
                      </div>
                    </div>
                    <button onClick={e => { e.stopPropagation(); deleteTask(task.id) }} className="text-slate-500 hover:text-red-400 p-1">×</button>
                  </div>
                  {task.progress && task.progress.percentage > 0 && task.progress.percentage < 100 && (
                    <div className="mt-2 h-1 bg-slate-700 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-cyan-500 to-purple-500 transition-all" style={{ width: `${task.progress.percentage}%` }} />
                    </div>
                  )}
                </div>
              ))}
              {tasks.length === 0 && <p className="text-center text-slate-500 py-8 text-sm">暂无任务</p>}
            </div>
          </aside>

          {/* Center: Flow + Detail */}
          <section className="flex-1 flex overflow-hidden">
            {/* Execution Flow Panel */}
            <div className="w-72 border-r border-cyan-500/20 bg-[#0a0e17]/30 flex flex-col">
              {/* 切换按钮 */}
              <div className="p-3 border-b border-cyan-500/10 flex gap-2">
                <button
                  onClick={() => setShowFlowView('stages')}
                  className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
                    showFlowView === 'stages'
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50' 
                      : 'bg-slate-800/50 text-slate-400 border border-slate-700 hover:border-slate-600'
                  }`}
                >
                  📋 阶段
                </button>
                <button
                  onClick={() => setShowFlowView('list')}
                  className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
                    showFlowView === 'list'
                      ? 'bg-purple-500/20 text-purple-400 border border-purple-500/50' 
                      : 'bg-slate-800/50 text-slate-400 border border-slate-700 hover:border-slate-600'
                  }`}
                >
                  🔀 列表
                </button>
                <button
                  onClick={() => setShowFlowView('dag')}
                  className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
                    showFlowView === 'dag'
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50' 
                      : 'bg-slate-800/50 text-slate-400 border border-slate-700 hover:border-slate-600'
                  }`}
                >
                  🔀 DAG
                </button>
              </div>

              {/* 内容区域 */}
              {showFlowView === 'dag' ? (
                /* DAG 水平流程图视图 (graph LR) */
                <ExecutionFlowDAG
                  flow={executionFlow}
                  onStepClick={(step) => setSelectedStep(step)}
                />
              ) : showFlowView === 'list' ? (
                /* 执行流程图视图 */
                <ExecutionFlowGraph 
                  flow={executionFlow} 
                  onStepClick={(step) => setSelectedStep(step)} 
                />
              ) : (
                /* 原有的阶段视图 */
                <div className="flex-1 overflow-auto p-5">
                  <h3 className="text-sm text-slate-400 mb-5">执行流程</h3>
                  <div className="relative" key={selectedTask?.stages?.map(s => s.status).join('-')}>
                    <div className="absolute left-5 top-0 bottom-0 w-px bg-gradient-to-b from-cyan-500/30 via-purple-500/30 to-emerald-500/30" />
                    {['主管规划', '任务分析', '任务分解', '智能体分配', '并行执行', '结果聚合'].map((name, i) => {
                      const stage = selectedTask?.stages?.[i]
                      const status = (stage?.status || 'pending') as string
                      const isSupervisor = i === 0
                      return (
                        <div key={`${i}-${status}`} className="relative flex items-center gap-4 mb-5">
                          <div className={`relative z-10 w-10 h-10 rounded-xl flex items-center justify-center border-2 transition-all ${
                            status === 'completed' ? 'bg-emerald-500/20 border-emerald-500' :
                            status === 'running' ? 'bg-cyan-500/20 border-cyan-500 animate-pulse' :
                            status === 'skipped' ? 'bg-slate-700/50 border-slate-500' :
                            'bg-slate-800 border-slate-600'}`}>
                            {status === 'completed' ? '✅' : status === 'running' ? '⏳' : status === 'skipped' ? '⏭️' : isSupervisor ? '👔' : <span className="text-slate-500">{i+1}</span>}
                          </div>
                          <div>
                            <p className={`text-sm font-medium ${status === 'completed' ? 'text-emerald-400' : status === 'running' ? 'text-white' : status === 'skipped' ? 'text-slate-500' : 'text-slate-500'}`}>{name}</p>
                            {stage?.details && <p className="text-xs text-slate-500">{stage.details}</p>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  {selectedTask?.status === 'completed' && (
                    <div className="mt-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                      <p className="text-sm text-emerald-400 flex items-center gap-2">✅ 任务完成</p>
                    </div>
                  )}
                  {(selectedTask as any)?.plan && (
                    <div className="mt-4 p-3 rounded-xl bg-purple-500/10 border border-purple-500/30">
                      <p className="text-sm text-purple-400 flex items-center gap-2">👔 主管已规划</p>
                      <p className="text-xs text-slate-400 mt-1">
                        {(selectedTask as any).plan.execution_plan?.length || 0} 个执行步骤
                      </p>
                      {(selectedTask as any).plan.execution_plan?.length > 0 && (
                        <button
                          onClick={() => setShowFlowView('dag')}
                          className="mt-2 text-xs text-cyan-400 hover:text-cyan-300 underline"
                        >
                          查看执行流程图 →
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Task Detail */}
            <div className="flex-1 bg-[#0a0e17]/30 flex flex-col overflow-hidden">
              {selectedTask ? (
                <>
                  <div className="p-5 border-b border-cyan-500/10">
                    <h2 className="text-lg font-semibold">{selectedTask.content}</h2>
                    <p className="text-xs text-slate-500 mt-1">ID: {selectedTask.id} · 状态: {selectedTask.status} · 输出类型: {selectedTask.output_type ?? 'report'}</p>
                  </div>
                  <div className="p-5 border-b border-cyan-500/10">
                    <h3 className="text-sm text-slate-400 mb-3">执行阶段</h3>
                    <div className="space-y-2">
                      {selectedTask.stages?.map((stage, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <div className="w-6 h-6 rounded-full bg-[#0a0e17] border border-slate-600 flex items-center justify-center text-xs text-slate-400">{i+1}</div>
                          <span className="text-sm">{stage.name}</span>
                          <div className={`w-2 h-2 rounded-full ${stage.status === 'completed' ? 'bg-emerald-500' : stage.status === 'running' ? 'bg-cyan-500 animate-pulse' : 'bg-slate-600'}`} />
                          {stage.details && <span className="text-xs text-slate-500">· {stage.details}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex-1 overflow-auto p-5">
                    {/* 最终报告展示 */}
                    {selectedTask.status === 'completed' && selectedTask.result && (
                      <div className="mb-6">
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="text-sm text-emerald-400 flex items-center gap-2">
                            📄 最终报告
                          </h3>
                          <div className="flex gap-2">
                            <button 
                              onClick={() => {
                                const content = selectedTask.result || ''
                                const blob = new Blob([content], { type: 'text/markdown' })
                                const url = URL.createObjectURL(blob)
                                const a = document.createElement('a')
                                a.href = url
                                a.download = `report_${selectedTask.id}.md`
                                a.click()
                                URL.revokeObjectURL(url)
                              }}
                              className="text-xs px-3 py-1 rounded-lg bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 transition-colors"
                            >
                              💾 下载
                            </button>
                            <button 
                              onClick={() => {
                                const content = selectedTask.result || ''
                                navigator.clipboard.writeText(content)
                              }}
                              className="text-xs px-3 py-1 rounded-lg bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 transition-colors"
                            >
                              📋 复制
                            </button>
                          </div>
                        </div>
                        <div className="p-5 rounded-xl bg-[#0a0e17] border border-emerald-500/30 max-h-[500px] overflow-auto">
                          <MarkdownRenderer content={selectedTask.result || ''} />
                        </div>
                      </div>
                    )}
                    
                    <h3 className="text-sm text-slate-400 mb-3">执行日志</h3>
                    <div className="space-y-2">
                      {(logs[selectedTask.id] || []).map((log, i) => (
                        <div key={i} className={`text-xs p-2 rounded-lg ${log.level === 'error' ? 'bg-red-500/10 text-red-400' : log.level === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-cyan-500/10 text-slate-300'}`}>
                          <span className="text-slate-500 mr-2">{new Date(log.timestamp).toLocaleTimeString()}</span>
                          {log.message}
                        </div>
                      ))}
                      {(logs[selectedTask.id] || []).length === 0 && <p className="text-slate-500 text-xs">等待执行日志...</p>}
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-5xl mb-4">🚀</div>
                    <h2 className="text-lg font-semibold mb-1">准备就绪</h2>
                    <p className="text-sm text-slate-500">输入任务描述，AI 员工团队将为你协作完成</p>
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* Right: Agents + Supervisor Panel */}
          <aside className="w-[420px] border-l border-cyan-500/20 bg-[#0a0e17]/50 flex flex-col overflow-hidden">
            {/* 主管面板 - 独立窗口式设计 */}
            {(() => {
              // 找到活跃的主管实例（动态创建的），或者使用模板
              const activeSupervisor = agents.find(a => a.role === 'supervisor' && a.status === 'running')
              const supervisorTemplate = agents.find(a => a.id === 'supervisor')
              const supervisor = activeSupervisor || supervisorTemplate
              
              // 直接传递所有 agentLogs 和 agentStreams，让 SupervisorPanel 自己过滤
              // 这样可以确保即使主管实例被释放，历史数据仍然可用
              
              // 优先使用按 task_id 索引的数据，回退到全局数据
              const currentTaskLogs = selectedId ? (taskAgentLogs[selectedId] || {}) : agentLogs
              const currentTaskStreams = selectedId ? (taskAgentStreams[selectedId] || {}) : agentStreams
              
              return supervisor ? (
                <SupervisorPanel
                  supervisor={supervisor}
                  currentTask={selectedTask}
                  agentLogs={currentTaskLogs}
                  agentStreams={currentTaskStreams}
                  allAgents={agents}
                  onClearData={clearSupervisorData}
                />
              ) : null
            })()}
          </aside>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

function StatCard({ label, value, icon, color }: { label: string; value: string | number; icon?: string; color?: string }) {
  const colorClasses: Record<string, string> = {
    cyan: 'bg-cyan-500/10 text-cyan-400',
    emerald: 'bg-emerald-500/10 text-emerald-400',
    purple: 'bg-purple-500/10 text-purple-400',
    default: 'bg-cyan-500/10 text-cyan-400',
  }
  const bgClass = colorClasses[color || 'default']
  
  return (
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-lg ${bgClass}`}>
        <span>{icon || '📊'}</span>
      </div>
      <div>
        <p className="text-xs text-slate-500">{label}</p>
        <p className="text-lg font-semibold">{value}</p>
      </div>
    </div>
  )
}

function TaskStatusIcon({ status }: { status: string }) {
  const icons: Record<string, string> = {
    pending: '⏸️', analyzing: '🔍', decomposing: '🔧', executing: '⚡', aggregating: '📊', completed: '✅', failed: '❌'
  }
  return <span className={status === 'executing' || status === 'analyzing' ? 'animate-pulse' : ''}>{icons[status] || '⏸️'}</span>
}
