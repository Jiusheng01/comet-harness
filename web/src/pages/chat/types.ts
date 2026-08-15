import { useEffect, useMemo, useRef, useState } from 'react'
import type { Citation, ToolCall, ToolRun } from '@/api/chat'

export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  toolCalls?: ToolCall[]
  toolRuns?: ToolRun[]
  images?: string[]
  attachments?: { file_name: string }[]
  streaming?: boolean
  conversationId?: string
  feedback?: 'up' | 'down' | null
  createdAt?: string
  fromHistory?: boolean
  traceId?: string
}
