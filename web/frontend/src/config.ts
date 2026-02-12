// API 配置 - 自动检测后端地址
const getApiBase = () => {
  // 如果是本地开发，使用 localhost
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:8000'
  }
  // 否则使用当前主机的 8000 端口
  return `http://${window.location.hostname}:8000`
}

const getWsBase = () => {
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'ws://localhost:8000'
  }
  return `ws://${window.location.hostname}:8000`
}

export const API_BASE = getApiBase()
export const WS_BASE = getWsBase()
