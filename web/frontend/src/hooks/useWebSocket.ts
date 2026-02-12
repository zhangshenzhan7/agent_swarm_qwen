import { useEffect, useRef, useState } from 'react'
import type { WSMessage } from '../types'

type MessageHandler = (message: WSMessage) => void

export function useWebSocket(url: string, onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null)
  const onMessageRef = useRef<MessageHandler>(onMessage)
  const [isConnected, setIsConnected] = useState(false)
  const reconnectTimeoutRef = useRef<number>()

  // 保持 onMessage 引用最新
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  useEffect(() => {
    let isMounted = true
    
    const connect = () => {
      if (!isMounted) return
      
      try {
        // 关闭旧连接
        if (wsRef.current) {
          wsRef.current.close()
        }
        
        const ws = new WebSocket(url)
        
        ws.onopen = () => {
          console.log('WebSocket connected')
          if (isMounted) setIsConnected(true)
        }
        
        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as WSMessage
            onMessageRef.current(message)
          } catch (e) {
            console.error('Failed to parse message:', e)
          }
        }
        
        ws.onclose = () => {
          console.log('WebSocket disconnected')
          if (isMounted) {
            setIsConnected(false)
            // 自动重连
            reconnectTimeoutRef.current = window.setTimeout(connect, 3000)
          }
        }
        
        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
        }
        
        wsRef.current = ws
      } catch (e) {
        console.error('Failed to connect:', e)
      }
    }
    
    connect()
    
    // 心跳
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
    
    return () => {
      isMounted = false
      clearInterval(heartbeat)
      clearTimeout(reconnectTimeoutRef.current)
      wsRef.current?.close()
    }
  }, [url])

  return { isConnected }
}
