import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Segmented,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  AppstoreOutlined,
  AuditOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  ShareAltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  memoryApi,
  type Insight,
  type MemoryHit,
  type MemoryItem,
  type MemoryListData,
  type MemoryProfile,
  type ProfileEntity,
  type ReviewOverview,
  type TimelineEvent,
} from '@/api/memories'
import ReviewPanel from '@/components/memory/ReviewPanel'

const { Text, Paragraph } = Typography

type TrustTone = 'high' | 'medium' | 'low'
type MemoryMode = 'overview' | 'search' | 'insights' | 'timeline' | 'review'

function trustTone(confidence?: number | null): TrustTone {
  const value = typeof confidence === 'number' ? confidence : 0.8
  if (value >= 0.85) return 'high'
  if (value >= 0.75) return 'medium'
  return 'low'
}

function trustLabel(confidence?: number | null) {
  const tone = trustTone(confidence)
  if (tone === 'high') return '高置信'
  if (tone === 'medium') return '中置信'
  return '待确认'
}

function trustColor(confidence?: number | null) {
  const tone = trustTone(confidence)
  if (tone === 'high') return 'success'
  if (tone === 'medium') return 'processing'
  return 'warning'
}

function trustPercent(confidence?: number | null) {
  const value = typeof confidence === 'number' ? confidence : 0.8
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
}

function TrustTag({ confidence }: { confidence?: number | null }) {
  const low = trustTone(confidence) === 'low'
  return (
    <Tooltip title={`置信度 ${trustPercent(confidence)}`}>
      <Tag
        color={trustColor(confidence)}
        icon={low ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
        style={{ margin: 0 }}
      >
        {trustLabel(confidence)}
      </Tag>
    </Tooltip>
  )
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function MemoryPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<MemoryMode>('overview')
  const [profile, setProfile] = useState<MemoryProfile | null>(null)
  const [overview, setOverview] = useState<ReviewOverview | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [recent, setRecent] = useState<MemoryListData | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [profileRes, overviewRes, insightsRes, recentRes] = await Promise.all([
        memoryApi.profile(),
        memoryApi.reviewOverview(),
        memoryApi.insights(),
        memoryApi.list(1, 6),
      ])
      setProfile(profileRes.data)
      setOverview(overviewRes.data)
      setInsights(insightsRes.data)
      setRecent(recentRes.data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const entities = useMemo(
    () => profile?.groups.flatMap((group) => group.entities) ?? [],
    [profile],
  )

  const topEntities = useMemo(() => {
    return [...entities]
      .sort((a, b) => {
        const layerDiff = Number(b.memory_layer === 'long_term') - Number(a.memory_layer === 'long_term')
        if (layerDiff !== 0) return layerDiff
        const importanceDiff = (b.importance ?? 0) - (a.importance ?? 0)
        if (Math.abs(importanceDiff) > 0.001) return importanceDiff
        return (b.access_count + b.mention_count) - (a.access_count + a.mention_count)
      })
      .slice(0, 6)
  }, [entities])

  const total = overview?.total_entities ?? profile?.total ?? entities.length
  const longTerm = overview?.long_term ?? entities.filter((entity) => entity.memory_layer === 'long_term').length
  const shortTerm = Math.max(0, total - longTerm)
  const pending = overview?.pending ?? 0
  const relationCount = overview?.total_relations ?? 0
  const avgConfidence = entities.length
    ? entities.reduce((sum, entity) => sum + (entity.confidence ?? 0.8), 0) / entities.length
    : 0

  const tabs = [
    { label: '概览', value: 'overview', icon: <AppstoreOutlined /> },
    { label: '记忆检索', value: 'search', icon: <SearchOutlined /> },
    { label: '洞察', value: 'insights', icon: <BulbOutlined /> },
    { label: '时间线', value: 'timeline', icon: <ClockCircleOutlined /> },
    {
      label: pending > 0 ? `审查与纠错 ${pending}` : '审查与纠错',
      value: 'review',
      icon: <AuditOutlined />,
    },
  ]

  return (
    <div className="fluid-page">
      <Card
        title="记忆"
        className="memory-card"
        extra={
          <Segmented
            className="memory-tabs"
            value={mode}
            onChange={(value) => setMode(value as MemoryMode)}
            options={tabs}
          />
        }
      >
        {mode === 'overview' ? (
          <OverviewPanel
            loading={loading}
            entities={entities}
            topEntities={topEntities}
            total={total}
            longTerm={longTerm}
            shortTerm={shortTerm}
            avgConfidence={avgConfidence}
            relationCount={relationCount}
            recent={recent?.items ?? []}
            insights={insights}
            onRefresh={load}
            onGraph={() => navigate('/graph')}
          />
        ) : mode === 'search' ? (
          <SearchPanel />
        ) : mode === 'insights' ? (
          <InsightsPanel insights={insights} loading={loading} onRefresh={load} />
        ) : mode === 'timeline' ? (
          <TimelinePanel />
        ) : (
          <ReviewPanel />
        )}
      </Card>
    </div>
  )
}

function OverviewPanel({
  loading,
  entities,
  topEntities,
  total,
  longTerm,
  shortTerm,
  avgConfidence,
  relationCount,
  recent,
  insights,
  onRefresh,
  onGraph,
}: {
  loading: boolean
  entities: ProfileEntity[]
  topEntities: ProfileEntity[]
  total: number
  longTerm: number
  shortTerm: number
  avgConfidence: number
  relationCount: number
  recent: MemoryItem[]
  insights: Insight[]
  onRefresh: () => void
  onGraph: () => void
}) {
  const longPercent = total > 0 ? Math.round((longTerm / total) * 100) : 0
  const shortPercent = total > 0 ? 100 - longPercent : 0

  if (loading && entities.length === 0) {
    return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <Text strong style={{ fontSize: 16 }}>记忆概览</Text>
          <div><Text type="secondary" style={{ fontSize: 12.5 }}>Memory Runtime 当前状态与核心记忆</Text></div>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>刷新</Button>
          <Button icon={<ShareAltOutlined />} onClick={onGraph}>打开记忆图谱</Button>
        </Space>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 10,
        }}
      >
        <StatBox label="实体总数" value={total} hint={`${new Set(entities.map((item) => item.type)).size} 个类型`} />
        <StatBox label="长期记忆" value={longTerm} hint={`${longPercent}%`} />
        <StatBox label="短期记忆" value={shortTerm} hint={`${shortPercent}%`} />
        <StatBox label="平均置信度" value={entities.length ? avgConfidence.toFixed(2) : '—'} hint={avgConfidence >= 0.85 ? '高置信' : '持续校准'} />
        <StatBox label="关联关系" value={relationCount} hint="Entity 语义关系" />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.45fr) minmax(300px, 0.85fr)',
          gap: 14,
          alignItems: 'stretch',
        }}
      >
        <Card size="small" title="核心实体（Top 6）" styles={{ body: { padding: 10 } }}>
          {topEntities.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无结构化记忆" />
          ) : (
            <div>
              {topEntities.map((entity, index) => (
                <CoreEntityRow key={entity.id} entity={entity} last={index === topEntities.length - 1} />
              ))}
            </div>
          )}
        </Card>

        <div style={{ display: 'grid', gridTemplateRows: 'auto 1fr', gap: 14 }}>
          <Card size="small" title="记忆层分布" styles={{ body: { padding: 14 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
              <div
                style={{
                  width: 96,
                  height: 96,
                  borderRadius: '50%',
                  background: `conic-gradient(#52c41a 0 ${longPercent}%, #155eef ${longPercent}% 100%)`,
                  display: 'grid',
                  placeItems: 'center',
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: 64,
                    height: 64,
                    borderRadius: '50%',
                    background: '#fff',
                    display: 'grid',
                    placeItems: 'center',
                    textAlign: 'center',
                  }}
                >
                  <div><div style={{ fontWeight: 700, fontSize: 20 }}>{total}</div><div style={{ fontSize: 11, color: '#98A2B3' }}>总数</div></div>
                </div>
              </div>
              <Space direction="vertical" size={6}>
                <Text><span style={{ color: '#52c41a' }}>●</span> 长期记忆　{longTerm}（{longPercent}%）</Text>
                <Text><span style={{ color: '#155eef' }}>●</span> 短期记忆　{shortTerm}（{shortPercent}%）</Text>
              </Space>
            </div>
          </Card>

          <Card size="small" title="最近活动" styles={{ body: { padding: '8px 14px' } }}>
            {recent.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无记忆任务" />
            ) : (
              recent.slice(0, 4).map((item, index) => (
                <div
                  key={item.id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '78px 1fr',
                    gap: 10,
                    padding: '8px 0',
                    borderBottom: index === Math.min(recent.length, 4) - 1 ? 'none' : '1px solid #f2f3f5',
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 11.5 }}>{formatTime(item.created_at)}</Text>
                  <div>
                    <Space size={5} wrap>
                      <Tag color={item.source === 'manual' ? 'purple' : 'blue'} style={{ margin: 0 }}>
                        {item.source === 'manual' ? '主动' : '自动'}
                      </Tag>
                      <Tag color={item.status === 'done' ? 'success' : item.status === 'failed' ? 'error' : 'processing'} style={{ margin: 0 }}>
                        {item.status}
                      </Tag>
                    </Space>
                    <div style={{ marginTop: 4, fontSize: 12.5, color: '#475467' }}>
                      {item.graph_stats
                        ? `新增 ${item.graph_stats.entities} 个实体，${item.graph_stats.relations} 个关系`
                        : item.raw_text.slice(0, 44)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </Card>
        </div>
      </div>

      {insights.length > 0 && (
        <div style={{ padding: '2px 2px 0' }}>
          <Space size={6}>
            <BulbOutlined style={{ color: '#155EEF' }} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              已生成 {insights.length} 条 Reflection 洞察，可在「洞察」标签查看。
            </Text>
          </Space>
        </div>
      )}
    </Space>
  )
}

function StatBox({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return (
    <div style={{ border: '1px solid #eef0f4', borderRadius: 10, padding: '12px 14px', background: '#fff' }}>
      <Text type="secondary" style={{ fontSize: 11.5 }}>{label}</Text>
      <div style={{ fontSize: 23, lineHeight: 1.35, fontWeight: 700, color: '#171719', marginTop: 3 }}>{value}</div>
      <Text type="secondary" style={{ fontSize: 11.5 }}>{hint}</Text>
    </div>
  )
}

function CoreEntityRow({ entity, last }: { entity: ProfileEntity; last: boolean }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '34px minmax(0, 1fr) auto',
        gap: 10,
        alignItems: 'center',
        padding: '10px 6px',
        borderBottom: last ? 'none' : '1px solid #f0f1f3',
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          background: entity.memory_layer === 'long_term' ? '#f0edff' : '#eef4ff',
          color: entity.memory_layer === 'long_term' ? '#6f42c1' : '#155eef',
          fontWeight: 700,
        }}
      >
        {entity.name.slice(0, 1)}
      </div>
      <div style={{ minWidth: 0 }}>
        <Space size={5} wrap>
          <Text strong>{entity.name}</Text>
          <Tag color="blue" style={{ margin: 0 }}>{entity.type}</Tag>
          <Tag color={entity.memory_layer === 'long_term' ? 'green' : 'default'} style={{ margin: 0 }}>
            {entity.memory_layer === 'long_term' ? '长期' : '短期'}
          </Tag>
        </Space>
        <div style={{ marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>{entity.description || entity.core_facts[0] || '暂无描述'}</Text>
        </div>
      </div>
      <Tooltip title={`置信度 ${trustPercent(entity.confidence)}`}>
        <Text style={{ color: entity.confidence >= 0.85 ? '#389e0d' : '#667085', fontSize: 12 }}>
          {entity.confidence.toFixed(2)}
        </Text>
      </Tooltip>
    </div>
  )
}

function SearchPanel() {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<MemoryHit[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)

  const search = async (value?: string) => {
    const q = (value ?? query).trim()
    if (!q) return
    setQuery(q)
    setSearching(true)
    setSearched(true)
    try {
      const { data } = await memoryApi.search(q, 12)
      setHits(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Text strong style={{ fontSize: 16 }}>记忆检索</Text>
        <div><Text type="secondary" style={{ fontSize: 12.5 }}>按语义和关键词从 Memory Graph 召回实体与一跳关系。</Text></div>
      </div>
      <Input.Search
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onSearch={search}
        enterButton="检索"
        loading={searching}
        allowClear
        size="large"
        placeholder="例如：我的工作方向、我最近在准备什么"
      />
      {searching ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : searched && hits.length === 0 ? (
        <Empty description="没有达到召回阈值的记忆" />
      ) : (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          {hits.map((hit) => (
            <Card key={hit.id} size="small" styles={{ body: { padding: 14 } }}>
              <Space size={6} wrap>
                <Text strong>{hit.name}</Text>
                <Tag color="blue" style={{ margin: 0 }}>{hit.type}</Tag>
                <TrustTag confidence={hit.confidence} />
                <Tag color={hit.memory_layer === 'long_term' ? 'green' : 'default'} style={{ margin: 0 }}>
                  {hit.memory_layer === 'long_term' ? '长期' : '短期'}
                </Tag>
                <Tag style={{ margin: 0 }}>score {hit.score}</Tag>
              </Space>
              {hit.description && <Paragraph type="secondary" style={{ margin: '6px 0' }}>{hit.description}</Paragraph>}
              {hit.relations.length > 0 && (
                <div style={{ borderLeft: '2px solid #eef4ff', paddingLeft: 10 }}>
                  {hit.relations.map((relation, index) => (
                    <div key={index} style={{ fontSize: 12.5, lineHeight: 1.8, color: '#475467' }}>
                      {hit.name} <Text type="secondary">{relation.predicate}</Text> {relation.object_name}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </Space>
      )}
    </Space>
  )
}

function InsightsPanel({ insights, loading, onRefresh }: { insights: Insight[]; loading: boolean; onRefresh: () => void }) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <Text strong style={{ fontSize: 16 }}>记忆洞察</Text>
          <div><Text type="secondary" style={{ fontSize: 12.5 }}>Reflection 从长期记忆中归纳出的高层结论。</Text></div>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>刷新</Button>
      </div>
      {loading && insights.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : insights.length === 0 ? (
        <Empty description="当前还没有 Reflection 洞察。记忆积累后后台任务会自动生成。" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(22rem, 100%), 1fr))', gap: 12 }}>
          {insights.map((insight) => (
            <Card key={insight.id} size="small" styles={{ body: { padding: 15 } }}>
              <Space size={5} wrap style={{ marginBottom: 7 }}>
                <Tag color="geekblue" style={{ margin: 0 }}>{insight.theme}</Tag>
                <TrustTag confidence={insight.confidence} />
              </Space>
              <Paragraph style={{ margin: 0, lineHeight: 1.7, color: '#344054' }}>{insight.content}</Paragraph>
              <div style={{ marginTop: 10 }}>
                <Text type="secondary" style={{ fontSize: 11.5 }}>来源 {insight.source_count} · importance {insight.importance.toFixed(2)}</Text>
              </div>
            </Card>
          ))}
        </div>
      )}
    </Space>
  )
}

function TimelinePanel() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    memoryApi.timeline()
      .then(({ data }) => setEvents(data))
      .catch((e) => message.error((e as Error).message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Text strong style={{ fontSize: 16 }}>事件时间线</Text>
        <div><Text type="secondary" style={{ fontSize: 12.5 }}>带明确时间语义的经历会被萃取为 Event Memory。</Text></div>
      </div>
      {events.length === 0 ? (
        <Empty description="当前没有事件记忆" />
      ) : (
        <div style={{ maxWidth: 900 }}>
          {events.map((event, index) => (
            <div key={event.id} style={{ display: 'grid', gridTemplateColumns: '120px 20px 1fr', gap: 10 }}>
              <Text type="secondary" style={{ fontSize: 12, paddingTop: 10 }}>{formatTime(event.event_time || event.created_at)}</Text>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', width: 10, height: 10, borderRadius: '50%', background: '#155eef', top: 13, left: 5 }} />
                {index < events.length - 1 && <span style={{ position: 'absolute', width: 2, background: '#e8edf7', top: 23, bottom: -14, left: 9 }} />}
              </div>
              <Card size="small" style={{ marginBottom: 12 }} styles={{ body: { padding: 12 } }}>
                <Text strong>{event.title}</Text>
                {event.description && <Paragraph type="secondary" style={{ margin: '5px 0 0' }}>{event.description}</Paragraph>}
                {event.participants.length > 0 && (
                  <Space wrap size={4} style={{ marginTop: 7 }}>
                    {event.participants.map((participant) => <Tag key={participant.id}>{participant.name}</Tag>)}
                  </Space>
                )}
              </Card>
            </div>
          ))}
        </div>
      )}
    </Space>
  )
}