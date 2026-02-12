import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText,
  Code,
  Image,
  Video,
  Globe,
  Package,
  ChevronDown,
  ChevronRight,
  File,
  Download,
} from 'lucide-react'
import type { OutputArtifact, ArtifactProgressEvent } from '../types'

interface ArtifactPanelProps {
  artifacts: OutputArtifact[]
  taskId: string
  progressEvents?: ArtifactProgressEvent[]
}

const STAGE_LABELS: Record<string, string> = {
  aggregating: '聚合中',
  generating: '生成中',
  validating: '验证中',
  storing: '存储中',
  completed: '已完成',
  failed: '失败',
}

const STAGE_COLORS: Record<string, string> = {
  aggregating: 'text-blue-400',
  generating: 'text-cyan-400',
  validating: 'text-yellow-400',
  storing: 'text-purple-400',
  completed: 'text-emerald-400',
  failed: 'text-red-400',
}

const STAGE_BG_COLORS: Record<string, string> = {
  aggregating: 'bg-blue-400',
  generating: 'bg-cyan-400',
  validating: 'bg-yellow-400',
  storing: 'bg-purple-400',
  completed: 'bg-emerald-400',
  failed: 'bg-red-400',
}

const TYPE_ICONS: Record<string, JSX.Element> = {
  report: <FileText className="w-4 h-4 text-cyan-400" />,
  code: <Code className="w-4 h-4 text-emerald-400" />,
  image: <Image className="w-4 h-4 text-purple-400" />,
  video: <Video className="w-4 h-4 text-pink-400" />,
  website: <Globe className="w-4 h-4 text-yellow-400" />,
  composite: <Package className="w-4 h-4 text-orange-400" />,
}

function getTypeIcon(outputType: string): JSX.Element {
  return TYPE_ICONS[outputType] ?? <File className="w-4 h-4 text-gray-400" />
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function getDownloadUrl(taskId: string, artifactId: string): string {
  return `/api/tasks/${taskId}/artifacts/${artifactId}/download`
}

export function ArtifactPanel({ artifacts, taskId, progressEvents }: ArtifactPanelProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const hasProgress = progressEvents && progressEvents.length > 0

  if (artifacts.length === 0 && !hasProgress) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm">
        暂无输出产物
      </div>
    )
  }

  const toggle = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  return (
    <div className="space-y-2 p-4">
      {hasProgress && <ProgressSection events={progressEvents} />}
      <h4 className="text-sm font-semibold text-gray-300 mb-3">输出产物</h4>
      <AnimatePresence>
        {artifacts.map((artifact) => (
          <ArtifactItem
            key={artifact.artifact_id}
            artifact={artifact}
            taskId={taskId}
            isExpanded={expandedId === artifact.artifact_id}
            onToggle={() => toggle(artifact.artifact_id)}
          />
        ))}
      </AnimatePresence>
    </div>
  )
}


function ProgressSection({ events }: { events: ArtifactProgressEvent[] }) {
  // Determine the overall current stage from the latest event
  const latestEvent = events[events.length - 1]
  const currentStage = latestEvent?.stage ?? 'generating'
  const stageLabel = STAGE_LABELS[currentStage] ?? currentStage
  const stageColor = STAGE_COLORS[currentStage] ?? 'text-gray-400'

  // Collect per-artifact progress events (for composite outputs)
  const artifactEvents = events.filter((e) => e.artifact_id)
  const artifactMap = new Map<string, ArtifactProgressEvent>()
  for (const evt of artifactEvents) {
    artifactMap.set(evt.artifact_id!, evt)
  }

  const isFailed = currentStage === 'failed'
  const isCompleted = currentStage === 'completed'

  return (
    <div className="mb-3 rounded-xl bg-[#0a0e17] border border-cyan-500/20 p-3 space-y-2">
      <div className="flex items-center gap-2">
        {!isCompleted && !isFailed && (
          <span className="relative flex h-2 w-2">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${STAGE_BG_COLORS[currentStage] ?? 'bg-cyan-400'}`} />
            <span className={`relative inline-flex rounded-full h-2 w-2 ${STAGE_BG_COLORS[currentStage] ?? 'bg-cyan-400'}`} />
          </span>
        )}
        <span className={`text-sm font-medium ${stageColor}`}>
          {stageLabel}
        </span>
        {latestEvent?.detail && (
          <span className="text-xs text-gray-500 truncate">{latestEvent.detail}</span>
        )}
      </div>

      {isFailed && latestEvent?.error && (
        <p className="text-xs text-red-400 bg-red-400/10 rounded-lg px-2 py-1">
          {latestEvent.error}
        </p>
      )}

      {artifactMap.size > 0 && (
        <div className="space-y-1.5 pt-1">
          {Array.from(artifactMap.entries()).map(([id, evt]) => (
            <ArtifactProgressRow key={id} event={evt} />
          ))}
        </div>
      )}
    </div>
  )
}


function ArtifactProgressRow({ event }: { event: ArtifactProgressEvent }) {
  const isFailed = event.stage === 'failed'
  const isCompleted = event.stage === 'completed'
  const progress = event.progress ?? 0
  const stageLabel = STAGE_LABELS[event.stage] ?? event.stage
  const barColor = isFailed ? 'bg-red-500' : isCompleted ? 'bg-emerald-500' : 'bg-cyan-500'

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-xs">
        <span className={`truncate ${isFailed ? 'text-red-400' : 'text-gray-300'}`}>
          {event.artifact_id}
          {event.output_type && <span className="text-gray-500 ml-1">({event.output_type})</span>}
        </span>
        <span className={`shrink-0 ml-2 ${isFailed ? 'text-red-400' : 'text-gray-500'}`}>
          {stageLabel}
        </span>
      </div>
      <div className="h-1 rounded-full bg-gray-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        />
      </div>
      {isFailed && event.error && (
        <p className="text-xs text-red-400">{event.error}</p>
      )}
    </div>
  )
}


interface ArtifactItemProps {
  artifact: OutputArtifact
  taskId: string
  isExpanded: boolean
  onToggle: () => void
}

function ArtifactItem({ artifact, taskId, isExpanded, onToggle }: ArtifactItemProps) {
  const validationColors: Record<string, string> = {
    valid: 'text-emerald-400',
    invalid: 'text-red-400',
    pending: 'text-yellow-400',
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="rounded-xl bg-[#0a0e17] border border-cyan-500/20 overflow-hidden"
    >
      {/* Header row */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-3 hover:bg-cyan-500/5 transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-gray-500 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500 shrink-0" />
        )}
        {getTypeIcon(artifact.output_type)}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white truncate">
            {artifact.artifact_id}.{artifact.metadata.format}
          </p>
          <p className="text-xs text-gray-500">
            {formatBytes(artifact.metadata.size_bytes)}
            <span className="mx-1">·</span>
            <span className={validationColors[artifact.validation_status] ?? 'text-gray-400'}>
              {artifact.validation_status}
            </span>
          </p>
        </div>
      </button>

      {/* Preview area */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-cyan-500/10"
          >
            <div className="p-3">
              <ArtifactPreview artifact={artifact} taskId={taskId} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

interface ArtifactPreviewProps {
  artifact: OutputArtifact
  taskId: string
}

function ArtifactPreview({ artifact, taskId }: ArtifactPreviewProps) {
  const url = getDownloadUrl(taskId, artifact.artifact_id)

  switch (artifact.output_type) {
    case 'report':
      return <ReportPreview url={url} />
    case 'code':
      return <CodePreview url={url} />
    case 'image':
      return <ImagePreview url={url} artifact={artifact} taskId={taskId} />
    case 'video':
      return <VideoPreview url={url} artifact={artifact} taskId={taskId} />
    case 'website':
      return (
        <iframe
          src={url}
          sandbox="allow-scripts"
          title={`preview-${artifact.artifact_id}`}
          className="w-full h-80 rounded-lg border border-cyan-500/10 bg-white"
        />
      )
    default:
      return <MetadataPreview artifact={artifact} />
  }
}

function ImagePreview({ url, artifact }: { url: string; artifact: OutputArtifact; taskId: string }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')

  return (
    <div className="space-y-2">
      {status === 'loading' && (
        <p className="text-xs text-gray-500 text-center py-4">图片加载中...</p>
      )}
      {status === 'error' && (
        <p className="text-xs text-red-400 text-center py-4">图片加载失败</p>
      )}
      <img
        src={url}
        alt={artifact.artifact_id}
        className={`max-w-full max-h-96 rounded-lg object-contain mx-auto ${status === 'loading' ? 'hidden' : ''}`}
        onLoad={() => setStatus('loaded')}
        onError={() => setStatus('error')}
      />
      {status === 'loaded' && (
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{artifact.metadata.format.toUpperCase()} · {formatBytes(artifact.metadata.size_bytes)}</span>
          <a
            href={`${url}?inline=false`}
            download={`${artifact.artifact_id}.${artifact.metadata.format}`}
            className="inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            <Download className="w-3 h-3" />
            下载
          </a>
        </div>
      )}
    </div>
  )
}

function VideoPreview({ url, artifact }: { url: string; artifact: OutputArtifact; taskId: string }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')

  return (
    <div className="space-y-2">
      {status === 'loading' && (
        <p className="text-xs text-gray-500 text-center py-4">视频加载中...</p>
      )}
      {status === 'error' && (
        <p className="text-xs text-red-400 text-center py-4">视频加载失败</p>
      )}
      <video
        src={url}
        controls
        preload="metadata"
        className={`max-w-full max-h-96 rounded-lg mx-auto ${status === 'loading' ? 'hidden' : ''}`}
        onLoadedMetadata={() => setStatus('loaded')}
        onError={() => setStatus('error')}
      >
        您的浏览器不支持视频播放
      </video>
      {status === 'loaded' && (
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{artifact.metadata.format.toUpperCase()} · {formatBytes(artifact.metadata.size_bytes)}</span>
          <a
            href={`${url}?inline=false`}
            download={`${artifact.artifact_id}.${artifact.metadata.format}`}
            className="inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            <Download className="w-3 h-3" />
            下载
          </a>
        </div>
      )}
    </div>
  )
}

function ReportPreview({ url }: { url: string }) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(url)
      .then((res) => (res.ok ? res.text() : Promise.reject()))
      .then(setContent)
      .catch(() => setError(true))
  }, [url])

  if (error) return <p className="text-xs text-red-400">加载失败</p>
  if (content === null) return <p className="text-xs text-gray-500">加载中...</p>

  return (
    <div
      className="prose prose-invert prose-sm max-w-none text-gray-300 overflow-auto max-h-96"
      dangerouslySetInnerHTML={{ __html: basicMarkdown(content) }}
    />
  )
}

function CodePreview({ url }: { url: string }) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(url)
      .then((res) => (res.ok ? res.text() : Promise.reject()))
      .then(setContent)
      .catch(() => setError(true))
  }, [url])

  if (error) return <p className="text-xs text-red-400">加载失败</p>
  if (content === null) return <p className="text-xs text-gray-500">加载中...</p>

  return (
    <pre className="overflow-auto max-h-96 rounded-lg bg-[#060a12] p-3 text-xs leading-relaxed">
      <code className="text-emerald-300 font-mono">{content}</code>
    </pre>
  )
}

function MetadataPreview({ artifact }: { artifact: OutputArtifact }) {
  const { metadata } = artifact
  return (
    <div className="text-xs text-gray-400 space-y-1">
      <p>类型: {artifact.output_type}</p>
      <p>格式: {metadata.format}</p>
      <p>MIME: {metadata.mime_type}</p>
      <p>大小: {formatBytes(metadata.size_bytes)}</p>
      <p>生成耗时: {metadata.generation_time_seconds.toFixed(1)}s</p>
      <p>创建时间: {new Date(artifact.created_at).toLocaleString('zh-CN')}</p>
    </div>
  )
}

/** Minimal markdown → HTML (headings, bold, italic, code, paragraphs) */
function basicMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
}
