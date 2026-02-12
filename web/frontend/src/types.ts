// AI 员工类型
export interface Agent {
  id: string
  name: string
  role: string
  description: string
  status: 'idle' | 'running' | 'completed' | 'failed'
  avatar: string
  current_task: string | null
  tools: string[]
  is_supervisor?: boolean
  is_instance?: boolean  // 是否是动态创建的实例
  instance_num?: number  // 实例编号
  parent_id?: string     // 父 agent ID（基础模板）
  stats?: {
    tasks_completed: number
    total_time?: number
    success_rate?: number
    direct_answers?: number
    delegated_tasks?: number
  }
}

// 执行阶段类型
export interface ExecutionStage {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  started_at?: string
  completed_at?: string
  details?: string
}

// 主管决策类型
export interface SupervisorDecision {
  decision_type: 'direct_answer' | 'delegate_swarm' | 'need_clarification'
  reasoning: string
  confidence: number
  direct_answer?: string
  task_analysis?: {
    complexity_score: number
    task_type: string
    required_capabilities: string[]
    suggested_agents: string[]
  }
  clarification_question?: string
  react_trace?: Array<{
    type: string
    content: string
  }>
}

// 输出产物类型
export interface OutputArtifact {
  artifact_id: string
  output_type: string
  metadata: {
    format: string
    size_bytes: number
    mime_type: string
    generation_time_seconds: number
  }
  validation_status: 'pending' | 'valid' | 'invalid'
  created_at: string
}

// 任务类型
export interface Task {
  id: string
  content: string
  status: string
  created_at: string
  completed_at?: string
  stages: ExecutionStage[]
  assigned_agents: string[]
  progress: {
    percentage: number
    current_stage: string
  }
  result?: string
  final_report?: string  // 总结员生成的最终报告
  error?: string
  decision?: SupervisorDecision
  clarification_question?: string
  plan?: {
    execution_plan?: any[]
    refined_task?: string
    key_objectives?: string[]
    suggested_agents?: string[]
  }
  files?: Array<{
    id: string
    name: string
    type: string
    size: number
    url: string
    base64?: string
  }>
  recommended_roles?: string[]
  output_type?: string
  artifacts?: OutputArtifact[]
}

// 执行日志类型
export interface LogEntry {
  timestamp: string
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
}

// 平台统计类型
export interface PlatformStats {
  total_tasks: number
  completed_tasks: number
  running_tasks: number
  pending_tasks: number
  total_agents: number
  active_agents: number
  success_rate: number
}

// WebSocket 消息类型
export interface WSMessage {
  type: string
  data: unknown
  timestamp: string
}

// 产物生成进度事件（WebSocket event type: "output_progress"）
export interface ArtifactProgressEvent {
  task_id: string
  stage: 'aggregating' | 'generating' | 'validating' | 'storing' | 'completed' | 'failed'
  artifact_id?: string
  output_type?: string
  detail?: string
  progress?: number
  error?: string
}

// 子任务执行流程节点
export interface SubTaskNode {
  step_id: string
  step_number: number
  name: string
  description: string
  agent_type: string
  expected_output: string
  dependencies: string[]
  status: 'pending' | 'waiting' | 'blocked' | 'running' | 'completed' | 'failed' | 'skipped'
  input_data?: Record<string, unknown>
  output_data?: Record<string, unknown>
  error?: string
  started_at?: string
  completed_at?: string
  agent_id?: string  // 执行该步骤的 agent 实例 ID
  agent_name?: string  // agent 名称
  logs?: LogEntry[]  // 执行日志
}

// 波次统计
export interface WaveStats {
  wave_number: number
  task_count: number
  parallelism: number
  start_time: number
  end_time: number
  completed_tasks: number
  failed_tasks: number
}

// 波次执行结果
export interface WaveExecutionResult {
  total_waves: number
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  blocked_tasks: number
  total_execution_time: number
  wave_stats?: WaveStats[]
}

// 执行流程图
export interface ExecutionFlowGraph {
  task_id: string
  steps: Record<string, SubTaskNode>
  execution_order: string[]
  progress: {
    total: number
    completed: number
    running: number
    failed: number
    progress_percent: number
  }
  wave_execution?: WaveExecutionResult
}
