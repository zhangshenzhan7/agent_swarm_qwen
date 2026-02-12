#!/bin/bash
#
# Qwen Agent Swarm — 部署脚本
# 支持 macOS / Ubuntu / Debian / CentOS / RHEL
#
# 使用方法:
#   chmod +x deploy.sh
#   ./deploy.sh              # 完整部署（安装依赖 + 构建 + 启动）
#   ./deploy.sh --start      # 仅启动服务
#   ./deploy.sh --stop       # 停止服务
#   ./deploy.sh --restart    # 重启服务
#   ./deploy.sh --status     # 查看状态
#   ./deploy.sh --logs       # 查看日志
#   ./deploy.sh --build      # 仅构建前端
#   ./deploy.sh --sdk        # 仅安装 SDK（不启动 Web 服务）
#   ./deploy.sh --docker     # 生成 Docker 部署文件
#   ./deploy.sh --systemd    # 安装 Systemd 服务（Linux only）
#

set -e

# ==================== 配置 ====================
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/web/backend"
FRONTEND_DIR="$PROJECT_DIR/web/frontend"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

BACKEND_PORT=8000
FRONTEND_PORT=3000
PYTHON_MIN_VERSION="3.10"
NODE_MIN_VERSION="18"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ==================== 工具函数 ====================
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[ OK ]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[FAIL]${NC} $1"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

version_ge() {
    [ "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}

get_os_type() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                echo "$ID"
            elif [ -f /etc/redhat-release ]; then
                echo "rhel"
            else
                echo "linux"
            fi
            ;;
        *) echo "unknown" ;;
    esac
}

create_directories() {
    mkdir -p "$LOG_DIR" "$PID_DIR" "$BACKEND_DIR/uploads"
}

# 健康检查：等待服务就绪
wait_for_service() {
    local url=$1 name=$2 max_attempts=${3:-15}
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

# ==================== 依赖检查与安装 ====================
check_python() {
    log_info "检查 Python 环境..."
    if command_exists python3; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if version_ge "$PYTHON_VERSION" "$PYTHON_MIN_VERSION"; then
            log_success "Python $PYTHON_VERSION"
            return 0
        fi
    fi

    log_warn "Python >= $PYTHON_MIN_VERSION 未找到，尝试安装..."
    OS_TYPE=$(get_os_type)
    case "$OS_TYPE" in
        macos)
            if command_exists brew; then
                brew install python@3.12
            else
                log_error "请先安装 Homebrew (https://brew.sh) 或手动安装 Python 3.10+"
                exit 1
            fi
            ;;
        ubuntu|debian)
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv
            ;;
        centos|rhel|fedora)
            sudo yum install -y python3 python3-pip python3-devel
            ;;
        *)
            log_error "不支持自动安装 Python，请手动安装 Python >= $PYTHON_MIN_VERSION"
            exit 1
            ;;
    esac
    log_success "Python 安装完成"
}

check_node() {
    log_info "检查 Node.js 环境..."
    if command_exists node; then
        NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
        if [ "$NODE_VERSION" -ge "$NODE_MIN_VERSION" ]; then
            log_success "Node.js $(node -v)"
            return 0
        fi
    fi

    log_warn "Node.js >= $NODE_MIN_VERSION 未找到，尝试安装..."
    OS_TYPE=$(get_os_type)
    case "$OS_TYPE" in
        macos)
            if command_exists brew; then
                brew install node@20
            else
                log_error "请先安装 Homebrew 或手动安装 Node.js 20+"
                exit 1
            fi
            ;;
        ubuntu|debian)
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt-get install -y -qq nodejs
            ;;
        centos|rhel|fedora)
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
            sudo yum install -y nodejs
            ;;
        *)
            log_error "不支持自动安装 Node.js，请手动安装 Node.js >= $NODE_MIN_VERSION"
            exit 1
            ;;
    esac
    log_success "Node.js 安装完成"
}

check_system_deps() {
    log_info "检查系统依赖..."
    OS_TYPE=$(get_os_type)
    case "$OS_TYPE" in
        macos)
            # macOS 自带 curl/git，检查 Xcode CLI tools
            if ! xcode-select -p >/dev/null 2>&1; then
                log_warn "安装 Xcode Command Line Tools..."
                xcode-select --install 2>/dev/null || true
            fi
            ;;
        ubuntu|debian)
            sudo apt-get update -qq
            sudo apt-get install -y -qq curl git build-essential
            ;;
        centos|rhel|fedora)
            sudo yum install -y curl git gcc gcc-c++ make
            ;;
    esac
    log_success "系统依赖就绪"
}

# ==================== 环境配置 ====================
setup_python_env() {
    log_info "配置 Python 虚拟环境..."

    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"

    pip install --upgrade pip -q

    # 安装 SDK + Web 依赖
    log_info "安装 Python 依赖..."
    pip install -e "$PROJECT_DIR[web]" -q

    log_success "Python 环境就绪"
}

setup_sdk_only() {
    log_info "仅安装 SDK..."

    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"

    pip install --upgrade pip -q
    pip install -e "$PROJECT_DIR" -q

    log_success "SDK 安装完成"
    echo ""
    echo "  激活环境: source .venv/bin/activate"
    echo "  使用示例: python -c \"from src import AgentSwarm; print('OK')\""
    echo ""
}

build_frontend() {
    log_info "构建前端..."
    cd "$FRONTEND_DIR"

    if [ -f "package-lock.json" ]; then
        npm ci --silent
    else
        npm install --silent
    fi

    npm run build
    cd "$PROJECT_DIR"
    log_success "前端构建完成"
}

setup_env_file() {
    local ENV_FILE="$BACKEND_DIR/.env"
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" << 'ENVEOF'
# DashScope API Key（阿里云百炼平台）
# 获取地址: https://dashscope.console.aliyun.com/
DASHSCOPE_API_KEY=

# 可选：阿里云沙箱配置（代码执行 + 浏览器工具）
# ALIYUN_ACCOUNT_ID=
# ALIYUN_ACCESS_KEY_ID=
# ALIYUN_ACCESS_KEY_SECRET=

# 服务配置
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
LOG_LEVEL=INFO
ENVEOF
        log_warn "已创建 $ENV_FILE，请编辑填入 DASHSCOPE_API_KEY"
    fi
}

# ==================== 服务管理 ====================
start_backend() {
    log_info "启动后端服务..."
    source "$VENV_DIR/bin/activate"
    cd "$BACKEND_DIR"

    if [ -f "$PID_DIR/backend.pid" ]; then
        local PID=$(cat "$PID_DIR/backend.pid")
        if kill -0 "$PID" 2>/dev/null; then
            log_warn "后端已在运行 (PID: $PID)"
            return 0
        fi
    fi

    nohup python -m uvicorn app:app \
        --host 0.0.0.0 \
        --port $BACKEND_PORT \
        --workers 2 \
        > "$LOG_DIR/backend.log" 2>&1 &

    echo $! > "$PID_DIR/backend.pid"
    cd "$PROJECT_DIR"

    if wait_for_service "http://localhost:$BACKEND_PORT/docs" "后端" 10; then
        log_success "后端服务启动成功 (端口: $BACKEND_PORT)"
    else
        log_warn "后端启动中，请稍后检查 $LOG_DIR/backend.log"
    fi
}

start_frontend() {
    log_info "启动前端服务..."
    cd "$FRONTEND_DIR"

    if [ -f "$PID_DIR/frontend.pid" ]; then
        local PID=$(cat "$PID_DIR/frontend.pid")
        if kill -0 "$PID" 2>/dev/null; then
            log_warn "前端已在运行 (PID: $PID)"
            return 0
        fi
    fi

    # 检查构建产物
    if [ ! -d "$FRONTEND_DIR/dist" ]; then
        log_warn "前端未构建，先执行构建..."
        build_frontend
    fi

    # 安装 serve（如果没有）
    if ! command_exists serve; then
        npm install -g serve --silent
    fi

    nohup serve -s dist -l $FRONTEND_PORT > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
    cd "$PROJECT_DIR"

    sleep 2
    if kill -0 $(cat "$PID_DIR/frontend.pid") 2>/dev/null; then
        log_success "前端服务启动成功 (端口: $FRONTEND_PORT)"
    else
        log_error "前端启动失败，查看 $LOG_DIR/frontend.log"
    fi
}

stop_service() {
    local name=$1 pid_file="$PID_DIR/$2.pid" process_pattern=$3
    log_info "停止${name}..."

    if [ -f "$pid_file" ]; then
        local PID=$(cat "$pid_file")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null || true
            sleep 1
            # 强制终止
            kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    fi

    # 清理残留进程
    if [ -n "$process_pattern" ]; then
        pkill -f "$process_pattern" 2>/dev/null || true
    fi

    log_success "${name}已停止"
}

start_services() {
    start_backend
    start_frontend
    echo ""
    log_success "=========================================="
    log_success "  Qwen Agent Swarm 启动成功"
    log_success "=========================================="
    echo ""
    echo "  前端:     http://localhost:$FRONTEND_PORT"
    echo "  后端 API: http://localhost:$BACKEND_PORT"
    echo "  API 文档: http://localhost:$BACKEND_PORT/docs"
    echo "  日志目录: $LOG_DIR"
    echo ""
}

stop_services() {
    stop_service "后端" "backend" "uvicorn app:app"
    stop_service "前端" "frontend" "serve -s dist"
}

restart_services() {
    stop_services
    sleep 2
    start_services
}

# ==================== 状态与日志 ====================
show_status() {
    echo ""
    echo "  Qwen Agent Swarm 服务状态"
    echo "  ────────────────────────────"

    for svc in backend frontend; do
        local pid_file="$PID_DIR/$svc.pid"
        local port=$( [ "$svc" = "backend" ] && echo $BACKEND_PORT || echo $FRONTEND_PORT )
        local label=$( [ "$svc" = "backend" ] && echo "后端" || echo "前端" )

        if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
            echo -e "  $label: ${GREEN}运行中${NC} (PID: $(cat "$pid_file"), 端口: $port)"
        else
            echo -e "  $label: ${RED}未运行${NC}"
        fi
    done
    echo ""
}

show_logs() {
    if [ ! -d "$LOG_DIR" ]; then
        log_error "日志目录不存在"
        return
    fi
    echo "  1) 后端日志  2) 前端日志  3) 全部"
    read -p "  选择 [1-3]: " choice
    case $choice in
        1) tail -f "$LOG_DIR/backend.log" ;;
        2) tail -f "$LOG_DIR/frontend.log" ;;
        3) tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" ;;
        *) log_error "无效选择" ;;
    esac
}

# ==================== Docker ====================
generate_docker_files() {
    log_info "生成 Docker 配置..."

    cat > "$PROJECT_DIR/Dockerfile" << 'DEOF'
# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY web/frontend/package*.json ./
RUN npm ci --silent
COPY web/frontend/ ./
RUN npm run build

# ---- Stage 2: Runtime ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir serve

COPY pyproject.toml ./
COPY src/ ./src/
COPY web/backend/ ./web/backend/

RUN pip install --no-cache-dir -e ".[web]"

COPY --from=frontend /app/frontend/dist ./web/frontend/dist

EXPOSE 8000 3000

CMD ["sh", "-c", "cd web/backend && uvicorn app:app --host 0.0.0.0 --port 8000 & npx serve -s web/frontend/dist -l 3000 & wait"]
DEOF

    cat > "$PROJECT_DIR/docker-compose.yml" << 'DCEOF'
services:
  app:
    build: .
    ports:
      - "8000:8000"
      - "3000:3000"
    env_file: web/backend/.env
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/docs"]
      interval: 30s
      timeout: 10s
      retries: 3
DCEOF

    cat > "$PROJECT_DIR/.dockerignore" << 'DIEOF'
.git
.venv
venv
__pycache__
*.pyc
node_modules
.env
logs/
pids/
artifacts/
*.log
.DS_Store
.kiro/
.pytest_cache/
*.egg-info/
DIEOF

    log_success "Docker 文件已生成: Dockerfile, docker-compose.yml, .dockerignore"
    echo ""
    echo "  启动: docker compose up -d"
    echo "  停止: docker compose down"
    echo ""
}

# ==================== Systemd（Linux only）====================
install_systemd_service() {
    if [ "$(get_os_type)" = "macos" ]; then
        log_error "Systemd 仅支持 Linux"
        exit 1
    fi

    log_info "安装 Systemd 服务..."

    sudo tee /etc/systemd/system/qwen-swarm-backend.service > /dev/null << EOF
[Unit]
Description=Qwen Agent Swarm Backend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$VENV_DIR/bin"
EnvironmentFile=$BACKEND_DIR/.env
ExecStart=$VENV_DIR/bin/python -m uvicorn app:app --host 0.0.0.0 --port $BACKEND_PORT --workers 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo tee /etc/systemd/system/qwen-swarm-frontend.service > /dev/null << EOF
[Unit]
Description=Qwen Agent Swarm Frontend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$FRONTEND_DIR
ExecStart=/usr/bin/npx serve -s dist -l $FRONTEND_PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable qwen-swarm-backend qwen-swarm-frontend

    log_success "Systemd 服务已安装"
    echo ""
    echo "  启动: sudo systemctl start qwen-swarm-backend qwen-swarm-frontend"
    echo "  状态: sudo systemctl status qwen-swarm-backend"
    echo ""
}

# ==================== 完整部署 ====================
full_deploy() {
    echo ""
    echo "  Qwen Agent Swarm — 部署"
    echo "  ════════════════════════"
    echo ""

    create_directories
    check_system_deps
    check_python
    check_node
    setup_python_env
    build_frontend
    setup_env_file
    start_services
}

# ==================== 帮助 ====================
show_help() {
    echo ""
    echo "Qwen Agent Swarm 部署脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "  (无参数)        完整部署（安装依赖 + 构建 + 启动）"
    echo "  --start         启动所有服务"
    echo "  --stop          停止所有服务"
    echo "  --restart       重启所有服务"
    echo "  --status        查看服务状态"
    echo "  --logs          查看服务日志"
    echo "  --build         仅构建前端"
    echo "  --sdk           仅安装 SDK（不启动 Web 服务）"
    echo "  --docker        生成 Docker 部署文件"
    echo "  --systemd       安装 Systemd 服务（Linux only）"
    echo "  --help          显示帮助"
    echo ""
}

# ==================== 主入口 ====================
main() {
    case "${1:-}" in
        --start)    create_directories; start_services ;;
        --stop)     stop_services ;;
        --restart)  restart_services ;;
        --status)   show_status ;;
        --logs)     show_logs ;;
        --build)    check_node; build_frontend ;;
        --sdk)      check_python; setup_sdk_only ;;
        --docker)   generate_docker_files ;;
        --systemd)  install_systemd_service ;;
        --help|-h)  show_help ;;
        "")         full_deploy ;;
        *)          log_error "未知选项: $1"; show_help; exit 1 ;;
    esac
}

main "$@"
