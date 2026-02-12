#!/bin/bash

# AI 员工运行平台启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# PID 文件
BACKEND_PID_FILE="/tmp/ai_platform_backend.pid"
FRONTEND_PID_FILE="/tmp/ai_platform_frontend.pid"

cleanup() {
    echo -e "\n${YELLOW}🛑 正在停止服务...${NC}"
    
    if [ -f "$BACKEND_PID_FILE" ]; then
        kill "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
        rm -f "$BACKEND_PID_FILE"
    fi
    
    if [ -f "$FRONTEND_PID_FILE" ]; then
        kill "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null || true
        rm -f "$FRONTEND_PID_FILE"
    fi
    
    echo -e "${GREEN}✅ 服务已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

check_port() {
    local port=$1
    if lsof -i :"$port" >/dev/null 2>&1; then
        echo -e "${RED}❌ 端口 $port 已被占用${NC}"
        return 1
    fi
    return 0
}

wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    echo -e "${RED}❌ $name 启动超时${NC}"
    return 1
}

echo -e "${GREEN}🚀 启动 AI 员工运行平台...${NC}"

# 检查端口
check_port 8000 || exit 1
check_port 3000 || exit 1

# 启动后端
echo -e "${YELLOW}📦 启动后端服务...${NC}"

# 激活虚拟环境
VENV_PATH="$SCRIPT_DIR/../.venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
    echo -e "${GREEN}✅ 已激活虚拟环境${NC}"
else
    echo -e "${YELLOW}⚠️  未找到虚拟环境，使用系统 Python${NC}"
fi

# 确定 Python 命令
if command -v python &>/dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    echo -e "${RED}❌ 未找到 Python${NC}"
    exit 1
fi

cd backend
$PYTHON_CMD -m pip install -r requirements.txt -q 2>/dev/null || true
$PYTHON_CMD app.py &
echo $! > "$BACKEND_PID_FILE"
cd "$SCRIPT_DIR"

# 等待后端就绪
if wait_for_service "http://localhost:8000/health" "后端"; then
    echo -e "${GREEN}✅ 后端服务已就绪${NC}"
else
    echo -e "${YELLOW}⚠️  后端健康检查未响应，继续启动...${NC}"
fi

# 启动前端
echo -e "${YELLOW}🎨 启动前端服务...${NC}"
cd frontend
npm install --silent 2>/dev/null || true
npm run dev &
echo $! > "$FRONTEND_PID_FILE"
cd "$SCRIPT_DIR"

# 等待前端就绪
sleep 3

echo ""
echo -e "${GREEN}✅ 平台已启动!${NC}"
echo -e "   后端: ${GREEN}http://localhost:8000${NC}"
echo -e "   前端: ${GREEN}http://localhost:3000${NC}"
echo ""
echo -e "按 ${YELLOW}Ctrl+C${NC} 停止所有服务"

# 保持运行
wait
