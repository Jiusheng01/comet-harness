import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface AgentConfig {
  enable_active_recall: boolean
  enable_cross_session: boolean
  show_avatar: boolean
  human_mode: boolean
}

export const agentConfigApi = {
  get() {
    return client.get<unknown, Wrapped<AgentConfig>>('/agent-config')
  },
  update(body: Partial<AgentConfig>) {
    return client.put<unknown, Wrapped<AgentConfig>>('/agent-config', body)
  },
}
