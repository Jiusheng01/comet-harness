import { useEffect, useMemo, useState } from 'react'
import { Button, Modal } from 'antd'
import {
  ArrowRightOutlined,
  BookOutlined,
  BulbOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CommentOutlined,
  ExperimentOutlined,
  FolderOpenOutlined,
  HddOutlined,
  MoreOutlined,
  SettingOutlined,
  ShareAltOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { dashboardApi, type DailyReview, type OverviewData } from '@/api/dashboard'
import { chatApi, type Conversation } from '@/api/chat'
import { researchApi, type ReportBrief } from '@/api/research'
import { agentTaskApi, type AgentTask } from '@/api/agentTask'
import { memoryApi } from '@/api/memories'
import { knowledgeBaseApi } from '@/api/knowledgeBases'
import { modelApi, type ModelConfigItem } from '@/api/models'
import { traceApi, type TraceListItem } from '@/api/traces'
import { useAuthStore } from '@/stores/authStore'
import heroIllustration from '@/images/home-hero.svg'
import './home.css'

const WELCOME_SEEN_KEY = 'comet_welcome_seen'

type RecentTab = 'chat' | 'research'

function formatRelative(value?: string | null) {
  if (!value) return '刚刚'
  const time = dayjs(value)
  if (!time.isValid()) return ''
  const now = dayjs()
  const minutes = now.diff(time, 'minute')
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = now.diff(time, 'hour')
  if (hours < 24) return `${hours} 小时前`
  if (now.diff(time, 'day') === 1) return `昨天 ${time.format('HH:mm')}`
  return time.format('MM-DD HH:mm')
}

function researchStatusText(status: ReportBrief['status']) {
  const labels: Record<ReportBrief['status'], string> = {
    pending: '等待开始',
    planning: '正在规划',
    searching: '正在检索',
    writing: '正在写作',
    summarizing: '正在收尾',
    done: '研究已完成',
    failed: '研究失败',
  }
  return labels[status]
}

function taskScheduleText(task: AgentTask) {
  if (task.trigger_type === 'interval') {
    return `每 ${task.trigger_interval_hours ?? '-'} 小时`
  }
  if (task.trigger_type === 'weekly') {
    const weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][
      task.trigger_weekday ?? 0
    ]
    return `每${weekday} ${task.trigger_time ?? ''}`.trim()
  }
  return `每天 ${task.trigger_time ?? ''}`.trim()
}

export default function HomePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  const [review, setReview] = useState<DailyReview | null>(null)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [models, setModels] = useState<ModelConfigItem[] | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [reports, setReports] = useState<ReportBrief[]>([])
  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [memoryTotal, setMemoryTotal] = useState(0)
  const [relationTotal, setRelationTotal] = useState(0)
  const [knowledgeBaseCount, setKnowledgeBaseCount] = useState(0)
  const [traces, setTraces] = useState<TraceListItem[]>([])
  const [traceLoaded, setTraceLoaded] = useState(false)
  const [recentTab, setRecentTab] = useState<RecentTab>('chat')
  const [welcomeOpen, setWelcomeOpen] = useState(false)

  const closeWelcome = () => {
    localStorage.setItem(WELCOME_SEEN_KEY, '1')
    setWelcomeOpen(false)
  }

  useEffect(() => {
    let cancelled = false
    let reviewTimer: ReturnType<typeof setTimeout> | null = null
    let reviewPolls = 0

    const fetchReview = () => {
      dashboardApi
        .dailyReview()
        .then(({ data }) => {
          if (cancelled) return
          setReview(data)
          if (data.generating && reviewPolls < 8) {
            reviewPolls += 1
            reviewTimer = setTimeout(fetchReview, 3000)
          }
        })
        .catch(() => {})
    }

    dashboardApi
      .overview()
      .then(({ data }) => {
        if (!cancelled) setOverview(data)
      })
      .catch(() => {})

    modelApi
      .list()
      .then(({ data }) => {
        if (!cancelled) setModels(data)
      })
      .catch(() => {
        if (!cancelled) setModels([])
      })

    chatApi
      .listConversations()
      .then(({ data }) => {
        if (!cancelled) setConversations(data.slice(0, 8))
      })
      .catch(() => {})

    researchApi
      .list(1, 8)
      .then(({ data }) => {
        if (!cancelled) setReports(data.items)
      })
      .catch(() => {})

    agentTaskApi
      .list()
      .then(({ data }) => {
        if (!cancelled) setTasks(data.filter((task) => task.enabled))
      })
      .catch(() => {})

    memoryApi
      .list(1, 1)
      .then(({ data }) => {
        if (!cancelled) setMemoryTotal(data.total)
      })
      .catch(() => {})

    memoryApi
      .reviewOverview(30)
      .then(({ data }) => {
        if (!cancelled) setRelationTotal(data.total_relations)
      })
      .catch(() => {})

    knowledgeBaseApi
      .list()
      .then(({ data }) => {
        if (!cancelled) setKnowledgeBaseCount(data.length)
      })
      .catch(() => {})

    traceApi
      .list({ days: 30, limit: 40 })
      .then(({ data }) => {
        if (cancelled) return
        setTraces(data.items)
        setTraceLoaded(true)
      })
      .catch(() => {
        if (!cancelled) setTraceLoaded(false)
      })

    fetchReview()

    return () => {
      cancelled = true
      if (reviewTimer) clearTimeout(reviewTimer)
    }
  }, [])

  const modelTypes = useMemo(
    () => new Set((models ?? []).map((model) => model.type)),
    [models],
  )
  const hasChatModel = modelTypes.has('chat') || modelTypes.has('multimodal')
  const hasEmbeddingModel = modelTypes.has('embedding')
  const needsSetup = models !== null && (!hasChatModel || !hasEmbeddingModel)

  useEffect(() => {
    if (needsSetup && !localStorage.getItem(WELCOME_SEEN_KEY)) {
      setWelcomeOpen(true)
    }
  }, [needsSetup])

  const displayName = user?.nickname || user?.email || user?.username || '朋友'
  const recentConversations = conversations.slice(0, 4)
  const recentReports = reports.slice(0, 4)
  const visibleTasks = [...tasks]
    .sort((a, b) => {
      if (!a.next_run_at) return 1
      if (!b.next_run_at) return -1
      return dayjs(a.next_run_at).valueOf() - dayjs(b.next_run_at).valueOf()
    })
    .slice(0, 2)

  const lastRecovery = traces.find((trace) =>
    /recover|recovery|恢复/i.test(`${trace.task_type} ${trace.task_name ?? ''}`),
  )
  const newestContent = overview?.recent?.[0]

  const knowledgeItems = [
    {
      label: '知识库',
      value: `${overview?.counts.documents ?? 0} 个文档`,
      icon: <BookOutlined />,
      tone: 'blue',
      to: '/knowledge',
    },
    {
      label: '记忆',
      value: `${memoryTotal} 条`,
      icon: <HddOutlined />,
      tone: 'green',
      to: '/memory',
    },
    {
      label: '关系图谱',
      value: `${relationTotal} 个关系`,
      icon: <ShareAltOutlined />,
      tone: 'orange',
      to: '/memory',
    },
    {
      label: '知识集',
      value: `${knowledgeBaseCount} 个集合`,
      icon: <FolderOpenOutlined />,
      tone: 'yellow',
      to: '/knowledge',
    },
  ]

  const runtimeItems = [
    {
      label: 'Agent Runtime',
      detail: traceLoaded ? '正常运行' : '待连接',
      healthy: traceLoaded,
    },
    {
      label: 'Checkpoint',
      detail: '已启用',
      healthy: true,
    },
    {
      label: 'Tool Runtime',
      detail: traceLoaded ? '正常' : '待连接',
      healthy: traceLoaded,
    },
    {
      label: 'Recovery',
      detail: lastRecovery ? '最近已恢复' : '正常待命',
      healthy: true,
    },
  ]

  return (
    <div className="comet-home">
      <section className="comet-hero">
        <div className="comet-hero__content">
          <div className="comet-hero__title">你好，{displayName} 👋</div>
          <div className="comet-hero__subtitle">今天想让 Comet 帮你做什么？</div>
          <div className="comet-hero__actions">
            <Button
              className="comet-hero__primary"
              icon={<CommentOutlined />}
              onClick={() => navigate('/chat')}
            >
              开始对话
            </Button>
            <Button
              className="comet-hero__secondary"
              icon={<ExperimentOutlined />}
              onClick={() => navigate('/research')}
            >
              深度研究
            </Button>
          </div>
        </div>
        <img className="comet-hero__art" src={heroIllustration} alt="Comet AI" />
      </section>

      {needsSetup && (
        <section className="comet-setup-strip">
          <div>
            <strong>先完成基础配置</strong>
            <span>
              {!hasChatModel ? '还缺对话模型' : ''}
              {!hasChatModel && !hasEmbeddingModel ? ' · ' : ''}
              {!hasEmbeddingModel ? '还缺向量模型' : ''}
            </span>
          </div>
          <Button type="primary" size="small" onClick={() => navigate('/settings/models')}>
            去配置 <ArrowRightOutlined />
          </Button>
        </section>
      )}

      <div className="comet-home__top-grid">
        <section className="comet-card comet-recent-card">
          <div className="comet-card__header">
            <span>最近使用</span>
          </div>
          <div className="comet-recent-tabs">
            <button
              type="button"
              className={recentTab === 'chat' ? 'is-active' : ''}
              onClick={() => setRecentTab('chat')}
            >
              最近对话
            </button>
            <button
              type="button"
              className={recentTab === 'research' ? 'is-active' : ''}
              onClick={() => setRecentTab('research')}
            >
              最近研究
            </button>
          </div>

          <div className="comet-recent-list">
            {recentTab === 'chat' && recentConversations.length === 0 && (
              <div className="comet-empty">还没有对话，去和 Comet 聊聊吧。</div>
            )}
            {recentTab === 'research' && recentReports.length === 0 && (
              <div className="comet-empty">还没有研究任务，试试发起一次深度研究。</div>
            )}

            {recentTab === 'chat' &&
              recentConversations.map((conversation, index) => (
                <button
                  type="button"
                  className={`comet-recent-item${index === 0 ? ' is-latest' : ''}`}
                  key={conversation.id}
                  onClick={() => navigate(`/chat?conversation=${conversation.id}`)}
                >
                  <span className="comet-recent-item__icon">
                    <CommentOutlined />
                  </span>
                  <span className="comet-recent-item__body">
                    <strong>{conversation.title || '未命名对话'}</strong>
                    <small>点击继续上次对话</small>
                  </span>
                  <span className="comet-recent-item__time">
                    {formatRelative(conversation.updated_at || conversation.created_at)}
                  </span>
                </button>
              ))}

            {recentTab === 'research' &&
              recentReports.map((report, index) => (
                <button
                  type="button"
                  className={`comet-recent-item${index === 0 ? ' is-latest' : ''}`}
                  key={report.id}
                  onClick={() => navigate('/research')}
                >
                  <span className="comet-recent-item__icon comet-recent-item__icon--research">
                    <ExperimentOutlined />
                  </span>
                  <span className="comet-recent-item__body">
                    <strong>{report.title || report.topic || '深度研究'}</strong>
                    <small>{researchStatusText(report.status)}</small>
                  </span>
                  <span className="comet-recent-item__time">{formatRelative(report.created_at)}</span>
                </button>
              ))}
          </div>

          <button
            type="button"
            className="comet-text-link comet-recent-card__more"
            onClick={() => navigate(recentTab === 'chat' ? '/chat' : '/research')}
          >
            {recentTab === 'chat' ? '查看全部对话' : '查看全部研究'} <ArrowRightOutlined />
          </button>
        </section>

        <div className="comet-home__right-stack">
          <section className="comet-card comet-review-card">
            <div className="comet-card__header">
              <span>
                <BulbOutlined /> 今日回顾
              </span>
            </div>
            <div className="comet-review-card__body">
              <div className="comet-review-card__copy">
                <strong>
                  {review?.content ||
                    (review?.generating ? '正在整理今天的回顾…' : '今天也在稳稳推进自己的事情。')}
                </strong>
                <p>{review?.care || '保持自己的节奏，明天继续把重要的事情做好。'}</p>
              </div>
              <div className="comet-review-card__cup" aria-hidden="true">
                ☕
              </div>
              <button
                type="button"
                className="comet-text-link comet-review-card__link"
                onClick={() =>
                  navigate(
                    review?.care
                      ? `/chat?greeting=${encodeURIComponent(review.care)}`
                      : '/chat',
                  )
                }
              >
                查看详情 <ArrowRightOutlined />
              </button>
            </div>
          </section>

          <section className="comet-card comet-task-card">
            <div className="comet-card__header comet-card__header--with-link">
              <span>
                <ClockCircleOutlined /> 自动任务
              </span>
              <button
                type="button"
                className="comet-text-link"
                onClick={() => navigate('/agent-tasks')}
              >
                查看全部 <ArrowRightOutlined />
              </button>
            </div>
            <div className="comet-task-list">
              {visibleTasks.length === 0 ? (
                <button
                  type="button"
                  className="comet-empty comet-empty--button"
                  onClick={() => navigate('/agent-tasks')}
                >
                  还没有启用的自动任务，去创建一个。
                </button>
              ) : (
                visibleTasks.map((task, index) => (
                  <button
                    type="button"
                    className="comet-task-item"
                    key={task.id}
                    onClick={() => navigate('/agent-tasks')}
                  >
                    <span
                      className={`comet-task-item__icon ${index % 2 ? 'is-purple' : 'is-green'}`}
                    >
                      {index % 2 ? <ExperimentOutlined /> : <ClockCircleOutlined />}
                    </span>
                    <span className="comet-task-item__body">
                      <strong>{task.name}</strong>
                      <small>{taskScheduleText(task)}</small>
                    </span>
                    <span className={`comet-task-item__next ${index % 2 ? 'is-orange' : ''}`}>
                      {task.next_run_at
                        ? `下次执行 ${dayjs(task.next_run_at).format('HH:mm')}`
                        : '等待调度'}
                    </span>
                    <MoreOutlined className="comet-task-item__more" />
                  </button>
                ))
              )}
            </div>
          </section>
        </div>
      </div>

      <div className="comet-home__bottom-grid">
        <section className="comet-card comet-knowledge-card">
          <div className="comet-card__header">
            <span>你的知识</span>
          </div>
          <div className="comet-knowledge-grid">
            {knowledgeItems.map((item) => (
              <button
                type="button"
                key={item.label}
                className={`comet-knowledge-item is-${item.tone}`}
                onClick={() => navigate(item.to)}
              >
                <span className="comet-knowledge-item__icon">{item.icon}</span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.value}</small>
                </span>
              </button>
            ))}
          </div>
          <div className="comet-knowledge-footer">
            <span>
              最近更新： <strong>{newestContent?.title || '暂无最近更新'}</strong>
              {newestContent?.time && <small>{formatRelative(newestContent.time)}</small>}
            </span>
            <button type="button" className="comet-text-link" onClick={() => navigate('/knowledge')}>
              进入知识库 <ArrowRightOutlined />
            </button>
          </div>
        </section>

        <section className="comet-card comet-runtime-card">
          <div className="comet-card__header">
            <span>
              <ThunderboltOutlined /> 运行状态
            </span>
          </div>
          <div className="comet-runtime-grid">
            {runtimeItems.map((item) => (
              <div className="comet-runtime-item" key={item.label}>
                <CheckCircleFilled className={item.healthy ? 'is-healthy' : 'is-muted'} />
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </span>
              </div>
            ))}
          </div>
          <div className="comet-runtime-footer">
            <span>
              最近恢复：{' '}
              {lastRecovery ? (
                <>
                  {formatRelative(lastRecovery.finished_at || lastRecovery.started_at)} ·{' '}
                  <strong className={lastRecovery.status === 'ok' ? 'is-success' : 'is-error'}>
                    {lastRecovery.status === 'ok'
                      ? '成功'
                      : lastRecovery.status === 'running'
                        ? '进行中'
                        : '失败'}
                  </strong>
                </>
              ) : (
                '暂无恢复记录'
              )}
            </span>
            <button type="button" className="comet-text-link" onClick={() => navigate('/traces')}>
              查看执行轨迹 <ArrowRightOutlined />
            </button>
          </div>
        </section>
      </div>

      <footer className="comet-home__footer">Powered by Comet Harness</footer>

      <Modal
        open={welcomeOpen}
        onCancel={closeWelcome}
        centered
        width={460}
        footer={null}
        title={null}
      >
        <div className="comet-welcome-modal">
          <div className="comet-welcome-modal__icon">
            <SettingOutlined />
          </div>
          <h2>欢迎使用 Comet</h2>
          <p>配置好对话模型和向量模型后，就可以使用对话、知识库、记忆和研究能力。</p>
          <div className="comet-welcome-modal__actions">
            <Button
              type="primary"
              onClick={() => {
                closeWelcome()
                navigate('/settings/models')
              }}
            >
              去配置模型
            </Button>
            <Button onClick={closeWelcome}>稍后再说</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
