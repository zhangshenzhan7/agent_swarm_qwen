# AI 员工运行平台

科技感十足的 AI 多智能体协作可视化平台。

## 功能特性

- 🤖 **AI 员工展示** - 8 种预定义 AI 角色，实时显示工作状态
- 📋 **任务管理** - 创建、跟踪、取消任务
- ⚡ **执行流程可视化** - 5 个阶段的执行进度展示
- 📊 **实时日志** - WebSocket 推送执行日志
- 🎨 **科技感 UI** - 霓虹风格、玻璃态效果、动画交互

## 快速启动

### 后端

```bash
cd web/backend
pip install -r requirements.txt
python app.py
```

后端运行在 http://localhost:8000

### 前端

```bash
cd web/frontend
npm install
npm run dev
```

前端运行在 http://localhost:3000

## 技术栈

### 后端
- FastAPI - 高性能 Web 框架
- WebSocket - 实时通信
- Pydantic - 数据验证

### 前端
- React 18 + TypeScript
- Tailwind CSS - 样式
- Framer Motion - 动画
- Recharts - 图表
- Lucide React - 图标

## API 接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/agents | 获取所有 AI 员工 |
| GET | /api/tasks | 获取所有任务 |
| POST | /api/tasks | 创建新任务 |
| GET | /api/tasks/{id} | 获取任务详情 |
| DELETE | /api/tasks/{id} | 取消任务 |
| GET | /api/stats | 获取平台统计 |
| WS | /ws | WebSocket 连接 |

## 执行阶段

1. **任务分析** - 评估任务复杂度
2. **任务分解** - 拆分为子任务
3. **智能体分配** - 分配 AI 员工
4. **并行执行** - 多智能体协作
5. **结果聚合** - 汇总执行结果
