import { useState } from 'react'
import { Download, Loader2, CheckCircle, AlertCircle } from 'lucide-react'

type DownloadState = 'idle' | 'downloading' | 'done' | 'error'

interface DownloadButtonProps {
  taskId: string
  artifactId: string
  filename: string
}

interface DownloadAllButtonProps {
  taskId: string
}

async function fetchAndDownload(url: string, filename: string, onProgress: (pct: number) => void): Promise<void> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Download failed: ${res.status}`)

  const contentLength = res.headers.get('Content-Length')
  const total = contentLength ? parseInt(contentLength, 10) : 0

  if (!res.body) {
    // Fallback: no streaming support
    const blob = await res.blob()
    triggerBrowserDownload(blob, filename)
    onProgress(100)
    return
  }

  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let received = 0

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.length
    if (total > 0) {
      onProgress(Math.round((received / total) * 100))
    }
  }

  const blob = new Blob(chunks as BlobPart[])
  triggerBrowserDownload(blob, filename)
  onProgress(100)
}

function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function DownloadButton({ taskId, artifactId, filename }: DownloadButtonProps) {
  const [state, setState] = useState<DownloadState>('idle')
  const [progress, setProgress] = useState(0)

  const handleClick = async () => {
    if (state === 'downloading') return
    setState('downloading')
    setProgress(0)
    try {
      const url = `/api/tasks/${taskId}/artifacts/${artifactId}/download`
      await fetchAndDownload(url, filename, setProgress)
      setState('done')
      setTimeout(() => setState('idle'), 2000)
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === 'downloading'}
      title={state === 'error' ? '下载失败，点击重试' : `下载 ${filename}`}
      className={`
        inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
        transition-all duration-200 cursor-pointer disabled:cursor-wait
        ${state === 'error'
          ? 'bg-red-500/10 text-red-400 border border-red-500/30'
          : 'bg-gradient-to-r from-cyan-500/10 to-purple-500/10 text-cyan-300 border border-cyan-500/20 hover:border-cyan-400/40 hover:text-white'
        }
      `}
    >
      <ButtonIcon state={state} />
      {state === 'downloading' && progress > 0 ? `${progress}%` : null}
    </button>
  )
}

export function DownloadAllButton({ taskId }: DownloadAllButtonProps) {
  const [state, setState] = useState<DownloadState>('idle')
  const [progress, setProgress] = useState(0)

  const handleClick = async () => {
    if (state === 'downloading') return
    setState('downloading')
    setProgress(0)
    try {
      const url = `/api/tasks/${taskId}/artifacts/download-all`
      await fetchAndDownload(url, `artifacts-${taskId}.zip`, setProgress)
      setState('done')
      setTimeout(() => setState('idle'), 2000)
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === 'downloading'}
      title={state === 'error' ? '打包下载失败，点击重试' : '打包下载全部产物 (ZIP)'}
      className={`
        inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
        transition-all duration-200 cursor-pointer disabled:cursor-wait
        ${state === 'error'
          ? 'bg-red-500/10 text-red-400 border border-red-500/30'
          : 'bg-gradient-to-r from-cyan-500/10 to-purple-500/10 text-cyan-300 border border-cyan-500/20 hover:border-cyan-400/40 hover:text-white'
        }
      `}
    >
      <ButtonIcon state={state} />
      <span>
        {state === 'downloading'
          ? progress > 0 ? `下载中 ${progress}%` : '打包中...'
          : state === 'done' ? '完成'
          : state === 'error' ? '失败'
          : '全部下载'}
      </span>
    </button>
  )
}

function ButtonIcon({ state }: { state: DownloadState }) {
  switch (state) {
    case 'downloading':
      return <Loader2 className="w-3.5 h-3.5 animate-spin" />
    case 'done':
      return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
    case 'error':
      return <AlertCircle className="w-3.5 h-3.5" />
    default:
      return <Download className="w-3.5 h-3.5" />
  }
}
