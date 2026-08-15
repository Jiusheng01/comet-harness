import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  Popconfirm,
  Progress,
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
  DeleteOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  ShareAltOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  memoryApi,
  type Insight,
  type MemoryHit,
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

export default function MemoryPage() {
  const [mode, setMode] = useState<MemoryMode>('overview')
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768,
  )

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const tabOptions = [
    { label: isMobile ? '概览' : '概览', value: 'overview', icon: <AppstoreOutlined /> },
    { label: isMobile ? '检索' : '记忆检索', value: 'search', icon: <SearchOutlined /> },
    { label: isMobile ? '洞察' : '记忆洞察', value: 'insights', icon: <BulbOutlined /> },
    { label: isMobile ? '时间' : '时间线', value: 'timeline', icon: <ClockCircleOutlined /> },
    { label: isMobile ? '审查' : '审查纠错', value: 'review', icon: <AuditOutlined /> },
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
            options={tabOptions}
          />
        }
      >
        {mode === 'overview' ? (
          <OverviewPanel />
        ) : mode === 'search' ? (
          <SearchPanel />
        ) : mode === 'insights' ? (
          <InsightsPanel />
        ) : mode === 'timeline' ? (
          <TimelinePanel />
        ) : (
          <ReviewPanel />
        )}
      </Card>
    </div>
  )
}

function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div
      style={{
        minWidth: 0,
        border: '1px solid #eef0f4',
        borderRadius: 12,
        padding: '14px 16px',
        background: '#fff',
      }}
    >
      <Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Text>
      <div style={{ fontSize: 24, lineHeight: 1.25, fontWeight: 700, color: '#171719', marginTop: 4 }}>
        {value}
      </div>
      {hint && (
        <Text type="secondary" style={{ fontSize: 11.5 }}>
          {hint}
        </Text>
      )}
    </div>
  )
}

function OverviewPanel() {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<MemoryProfile | null>(null)
  const [overview, setOverview] = useState<ReviewOverview | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [profileRes, overviewRes] = await Promise.all([
        memoryApi.profile(),
        memoryApi.reviewOverview(),
      ])
      setProfile(profileRes.data)
      setOverview(overviewRes.data)
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

  const longTerm = overview?.long_term ?? entities.filter((e) => e.memory_layer === 'long_term').length
  const total = overview?.total_entities ?? profile?.total ?? entities.length
  const shortTerm = Math.max(0, total - longTerm)
  const relationCount = overview?.total_relations ?? 0
  const pending = overview?.pending ?? 0
  const verified = overview?.verified ?? 0
  const recentAdded = overview?.trend.reduce((sum, item) => sum + item.count, 0) ?? 0
  const avgConfidence = entities.length
    ? entities.reduce((sum, entity) => sum + (entity.confidence ?? 0.8), 0) / entities.length
    : 0
  const longTermPercent = total > 0 ? Math.round((longTerm / total) * 100) : 0

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

  if (loading && !profile) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin />
      </div>
    )
  }

  return (
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <Text strong style={{ fontSize: 16 }}>
            Memory Runtime 概览
          </Text>
          <div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              查看系统记住了什么、短期/长期分层、质量状态以及当前可召回的核心实体。
            </Text>
          </div>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
          <Button icon={<ShareAltOutlined />} onClick={() => navigate('/graph')}>
            打开记忆图谱
          </Button>
        </Space>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 12,
        }}
      >
        <StatCard label="实体总数" value={total} hint={`${profile?.groups.length ?? 0} 个类型`} />
        <StatCard label="长期记忆" value={longTerm} hint={`${longTermPercent}% 已巩固`} />
        <StatCard label="短期记忆" value={shortTerm} hint="等待复用或巩固" />
        <StatCard label="平均置信度" value={entities.length ? avgConfidence.toFixed(2) : '—'} hint={`${pending} 条待确认`} />
        <StatCard label="关系数" value={relationCount} hint="Entity 一跳语义关系" />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))',
          gap: 14,
        }}
      >
        <Card size="small" title="记忆生命周期" styles={{ body: { padding: 16 } }}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <Text>长期记忆占比</Text>
                <Text type="secondary">{longTerm} / {total}</Text>
              </div>
              <Progress percent={longTermPercent} showInfo={false} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
              <StatCard label="待确认" value={pending} />
              <StatCard label="人工确认" value={verified} />
              <StatCard label={`近 ${overview?.days ?? 30} 天新增`} value={recentAdded} />
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              新实体默认进入 short-term；被反复检索、反复提及或重要度达标后，由 Consolidation 晋升为 long-term。
            </Text>
          </Space>
        </Card>

        <Card size="small" title="Runtime 说明" styles={{ body: { padding: 16 } }}>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <div>
              <Text strong>写入</Text>
              <div><Text type="secondary">对话结束后异步萃取 Statement / Entity / Relation / Event。</Text></div>
            </div>
            <div>
              <Text strong>召回</Text>
              <div><Text type="secondary">向量检索 + 全文检索 + 一跳关系扩展，并结合置信度和记忆层排序。</Text></div>
            </div>
            <div>
              <Text strong>图谱</Text>
              <div><Text type="secondary">节点、关系、社区和来源溯源统一放在独立「记忆图谱」页面探索。</Text></div>
            </div>
          </Space>
        </Card>
      </div>

      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            gap: 12,
            marginBottom: 10,
          }}
        >
          <div>
            <Text strong style={{ fontSize: 15 }}>核心实体</Text>
            <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
              优先展示长期、高重要度和高复用实体
            </Text>
          </div>
          {entities.length > topEntities.length && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              当前共 {entities.length} 个实体
            </Text>
          )}
        </div>

        {topEntities.length === 0 ? (
          <Empty description="还没有结构化记忆。正常对话会自动进入异步记忆萃取。" />
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(min(18rem, 100%), 1fr))',
              gap: 12,
            }}
          >
            {topEntities.map((entity) => <EntityCard key={entity.id} entity={entity} />)}
          </div>
        )}
      </div>

      <AdvancedMemoryOps onChanged={load} />
    </Space>
  )
}

function EntityCard({ entity }: { entity: ProfileEntity }) {
  return (
    <Card
      size="small"
      className={trustTone(entity.confidence) === 'low' ? 'memory-entity-card memory-entity-card--weak' : 'memory-entity-card'}
      styles={{ body: { padding: 14 } }}
    >
      <Space size={5} wrap style={{ marginBottom: 6 }}>
        <Text strong style={{ fontSize: 14.5 }}>{entity.name}</Text>
        <Tag color="blue" style={{ margin: 0 }}>{entity.type}</Tag>
        <TrustTag confidence={entity.confidence} />
        <Tag color={entity.memory_layer === 'long_term' ? 'gold' : 'default'} style={{ margin: 0 }}>
          {entity.memory_layer === 'long_term' ? '长期' : '短期'}
        </Tag>
      </Space>

      {entity.description && (
        <Paragraph
          type="secondary"
          style={{ margin: '2px 0 8px', fontSize: 12.5 }}
          ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
        >
          {entity.description}
        </Paragraph>
      )}

      {entity.relations.length > 0 && (
        <div style={{ paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
          {entity.relations.slice(0, 3).map((relation, index) => (
            <div key={index} style={{ fontSize: 12, color: '#475467', lineHeight: 1.8 }}>
              <Text type="secondary">{relation.predicate}</Text> {relation.object_name}
            </div>
          ))}
        </div>
      )}

      {(entity.core_facts.length > 0 || entity.traits.length > 0) && (
        <Space size={4} wrap style={{ marginTop: 8 }}>
          {entity.core_facts.slice(0, 2).map((fact) => (
            <Tag key={fact} color="processing" style={{ margin: 0 }}>{fact}</Tag>
          ))}
          {entity.traits.slice(0, 2).map((trait) => (
            <Tag key={trait} color="purple" style={{ margin: 0 }}>{trait}</Tag>
          ))}
        </Space>
      )}
    </Card>
  )
}

function AdvancedMemoryOps({ onChanged }: { onChanged: () => void }) {
  const [text, setText] = useState('')
  const [remembering, setRemembering] = useState(false)
  const [consolidating, setConsolidating] = useState(false)
  const [reflecting, setReflecting] = useState(false)
  const [clustering, setClustering] = useState(false)

  const onRemember = async () => {
    const value = text.trim()
    if (!value) {
      message.warning('请输入要写入的记忆内容')
      return
    }
    setRemembering(true)
    try {
      await memoryApi.remember(value)
      setText('')
      message.success('已提交异步记忆萃取；完成后刷新概览即可看到结果')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setRemembering(false)
    }
  }

  const onConsolidate = async () => {
    setConsolidating(true)
    try {
      const { data } = await memoryApi.consolidate()
      message.success(
        `巩固完成：${data.promoted_entities} 个实体、${data.promoted_statements} 条陈述晋升，增强 ${data.enhanced_profiles} 个画像`,
      )
      onChanged()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setConsolidating(false)
    }
  }

  const onReflect = async () => {
    setReflecting(true)
    try {
      const { data } = await memoryApi.reflect()
      message.success(data.insights > 0 ? `Reflection 完成：生成或更新 ${data.insights} 条洞察` : 'Reflection 完成：当前信息不足以生成新洞察')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setReflecting(false)
    }
  }

  const onRecluster = async () => {
    setClustering(true)
    try {
      await memoryApi.recluster()
      message.success('记忆社区重新聚类完成')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setClustering(false)
    }
  }

  return (
    <Collapse
      size="small"
      items={[
        {
          key: 'advanced',
          label: '高级操作 · 手动写入 / 巩固 / Reflection / 聚类',
          children: (
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              <div>
                <Text strong>手动添加记忆</Text>
                <div style={{ margin: '6px 0 8px' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    正常对话已经会自动萃取。这里只用于显式写入希望系统保留的事实。
                  </Text>
                </div>
                <Space.Compact style={{ width: '100%' }}>
                  <Input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onPressEnter={onRemember}
                    placeholder="例如：我的主力语言是 Python"
                    allowClear
                  />
                  <Button type="primary" icon={<PlusOutlined />} loading={remembering} onClick={onRemember}>
                    添加
                  </Button>
                </Space.Compact>
              </div>

              <Space wrap>
                <Button loading={consolidating} onClick={onConsolidate}>
                  运行 Consolidation
                </Button>
                <Button icon={<ThunderboltOutlined />} loading={reflecting} onClick={onReflect}>
                  运行 Reflection
                </Button>
                <Button icon={<ReloadOutlined />} loading={clustering} onClick={onRecluster}>
                  重新聚类
                </Button>
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                这些操作主要用于调试和验证；生产环境中的巩固、Reflection、聚类可由后台任务自动执行。
              </Text>
            </Space>
          ),
        },
      ]}
    />
  )
}

function SearchPanel() {
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<MemoryHit[]>([])

  const onSearch = async () => {
    const q = query.trim()
    if (!q) {
      message.warning('请输入检索关键词')
      return
    }
    setSearching(true)
    try {
      const { data } = await memoryApi.search(q, 10)
      setHits(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Text strong style={{ fontSize: 16 }}>Memory Retrieval</Text>
        <div>
          <Text type="secondary" style={{ fontSize: 12.5 }}>
            直接测试当前记忆召回：语义向量 + 全文检索 + 实体一跳关系扩展。
          </Text>
        </div>
      </div>

      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={onSearch}
          placeholder="例如：我的技术方向、正在准备的面试、最近关注的系统问题"
          size="large"
          allowClear
        />
        <Button type="primary" size="large" loading={searching} icon={<SearchOutlined />} onClick={onSearch}>
          检索
        </Button>
      </Space.Compact>

      {hits.length === 0 ? (
        <Empty description="输入查询，查看 Memory Runtime 实际会召回哪些实体与关系" />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {hits.map((hit) => (
            <Card key={hit.id} size="small" styles={{ body: { padding: 16 } }}>
              <Space size="small" style={{ marginBottom: 6 }} wrap>
                <Text strong>{hit.name}</Text>
                <Tag color="blue">{hit.type}</Tag>
                <TrustTag confidence={hit.confidence} />
                <Tag color={hit.memory_layer === 'long_term' ? 'gold' : 'default'}>
                  {hit.memory_layer === 'long_term' ? '长期' : '短期'}
                </Tag>
                <Tooltip title="融合相关度">
                  <Tag>score {hit.score}</Tag>
                </Tooltip>
              </Space>
              {hit.description && (
                <Paragraph type="secondary" style={{ margin: '4px 0 8px' }}>
                  {hit.description}
                </Paragraph>
              )}
              {hit.relations.length > 0 && (
                <div style={{ paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
                  {hit.relations.map((relation, index) => (
                    <div key={index} style={{ fontSize: 13, color: '#475467', lineHeight: 1.8 }}>
                      {trustTone(relation.confidence) === 'low' && (
                        <Tag color="warning" style={{ marginRight: 6, fontSize: 11, lineHeight: '16px' }}>
                          待确认
                        </Tag>
                      )}
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

function InsightsPanel() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await memoryApi.insights()
      setInsights(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const onDelete = async (id: string) => {
    try {
      await memoryApi.deleteInsight(id)
      setInsights((prev) => prev.filter((item) => item.id !== id))
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <Space size={8}>
            <BulbOutlined style={{ color: '#155EEF' }} />
            <Text strong style={{ fontSize: 16 }}>记忆洞察</Text>
          </Space>
          <div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              Reflection 从长期实体与代表性陈述中归纳出的高层结论，不等同于原始事实。
            </Text>
          </div>
        </div>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          刷新
        </Button>
      </div>

      {loading && insights.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : insights.length === 0 ? (
        <Empty description="暂无洞察。记忆积累后由后台 Reflection 生成，也可在「概览 > 高级操作」手动运行。" />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(min(20rem, 100%), 1fr))',
            gap: 12,
          }}
        >
          {insights.map((insight) => (
            <Card key={insight.id} size="small" styles={{ body: { padding: 15 } }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                <Space size={5} wrap>
                  <Tag color="geekblue" style={{ margin: 0 }}>{insight.theme}</Tag>
                  <TrustTag confidence={insight.confidence} />
                </Space>
                <Popconfirm title="删除这条派生洞察？" onConfirm={() => onDelete(insight.id)}>
                  <DeleteOutlined style={{ color: '#C0C4CC' }} />
                </Popconfirm>
              </div>
              <Paragraph style={{ margin: 0, color: '#344054', lineHeight: 1.7 }}>
                {insight.content}
              </Paragraph>
              <div style={{ marginTop: 10 }}>
                <Text type="secondary" style={{ fontSize: 11.5 }}>
                  来源实体 {insight.source_count} · importance {insight.importance.toFixed(2)}
                </Text>
              </div>
            </Card>
          ))}
        </div>
      )}
    </Space>
  )
}

type TimeBucket = {
  key: string
  label: string
  hint?: string
  order: number
  events: TimelineEvent[]
}

function bucketize(events: TimelineEvent[]): TimeBucket[] {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86_400_000)
  const week7Ago = new Date(today.getTime() - 6 * 86_400_000)
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']

  const buckets: Record<string, TimeBucket> = {}
  const put = (key: string, label: string, order: number, event: TimelineEvent, hint?: string) => {
    if (!buckets[key]) buckets[key] = { key, label, hint, order, events: [] }
    buckets[key].events.push(event)
  }

  for (const event of events) {
    const raw = event.event_time || event.created_at
    if (!raw) {
      put('unknown', '时间未知', 99999, event)
      continue
    }
    const date = new Date(raw)
    if (Number.isNaN(date.getTime())) {
      put('unknown', '时间未知', 99999, event)
      continue
    }
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate())
    const hint = `${date.getMonth() + 1} 月 ${date.getDate()} 日 · 周${weekdays[date.getDay()]}`

    if (day.getTime() === today.getTime()) {
      put('today', '今天', 0, event, hint)
    } else if (day.getTime() === yesterday.getTime()) {
      put('yesterday', '昨天', 1, event, hint)
    } else if (day >= week7Ago && day < yesterday) {
      put('week', '近 7 天', 2, event)
    } else if (day >= monthStart && day < week7Ago) {
      put('month', '本月更早', 3, event)
    } else {
      const ym = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const order = 10 - date.getTime() / 1e13
      put(ym, `${date.getFullYear()} 年 ${date.getMonth() + 1} 月`, order, event)
    }
  }

  return Object.values(buckets).sort((a, b) => a.order - b.order)
}

function TimelinePanel() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    memoryApi
      .timeline()
      .then(({ data }) => setEvents(data))
      .catch((e) => message.error((e as Error).message))
      .finally(() => setLoading(false))
  }, [])

  const buckets = useMemo(() => bucketize(events), [events])

  const fmtEventTime = (event: TimelineEvent, bucketKey: string) => {
    const raw = event.event_time || event.created_at
    if (!raw) return '时间未知'
    const date = new Date(raw)
    if (Number.isNaN(date.getTime())) return String(raw)
    if (bucketKey === 'today' || bucketKey === 'yesterday') {
      const hh = String(date.getHours()).padStart(2, '0')
      const mm = String(date.getMinutes()).padStart(2, '0')
      return `${hh}:${mm}`
    }
    return `${date.getMonth() + 1}月${date.getDate()}日`
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
  }

  if (events.length === 0) {
    return <Empty description="还没有事件。对话中包含明确时间的经历会被萃取为 Event Memory。" />
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          background: '#f7f9fc',
          border: '1px solid #eef0f4',
          borderRadius: 12,
          marginBottom: 18,
        }}
      >
        <ClockCircleOutlined style={{ color: '#155EEF', fontSize: 16 }} />
        <Text strong style={{ fontSize: 14 }}>Event Memory · {events.length} 条</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>按事件时间倒序组织</Text>
      </div>

      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        {buckets.map((bucket) => (
          <div key={bucket.key}>
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 10,
                marginBottom: 12,
                paddingBottom: 6,
                borderBottom: '1px solid #f0f1f3',
              }}
            >
              <Text strong style={{ fontSize: 15 }}>{bucket.label}</Text>
              {bucket.hint && <Text type="secondary" style={{ fontSize: 12.5 }}>{bucket.hint}</Text>}
              <div style={{ flex: 1 }} />
              <Tag>{bucket.events.length} 条</Tag>
            </div>

            <div style={{ paddingLeft: 8 }}>
              {bucket.events.map((event, index) => (
                <div
                  key={event.id}
                  style={{
                    position: 'relative',
                    paddingLeft: 28,
                    paddingBottom: index === bucket.events.length - 1 ? 0 : 14,
                    borderLeft: index === bucket.events.length - 1 ? 'none' : '2px solid #EEF4FF',
                    marginLeft: 6,
                  }}
                >
                  <span
                    style={{
                      position: 'absolute',
                      left: -7,
                      top: 8,
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      background: '#155EEF',
                      border: '2px solid #ffffff',
                      boxShadow: '0 0 0 2px #EEF4FF',
                    }}
                  />
                  <Text style={{ fontSize: 12, color: '#155EEF', fontWeight: 600 }}>
                    {fmtEventTime(event, bucket.key)}
                  </Text>
                  <div
                    style={{
                      marginTop: 4,
                      background: '#ffffff',
                      border: '1px solid #eef0f4',
                      borderRadius: 10,
                      padding: '10px 14px',
                    }}
                  >
                    <Text strong style={{ fontSize: 14.5, display: 'block' }}>{event.title}</Text>
                    {event.description && (
                      <Paragraph
                        type="secondary"
                        style={{ margin: '4px 0 0', fontSize: 13 }}
                        ellipsis={{ rows: 2, tooltip: event.description }}
                      >
                        {event.description}
                      </Paragraph>
                    )}
                    {event.participants.length > 0 && (
                      <Space size={4} wrap style={{ marginTop: 8 }}>
                        {event.participants.map((participant) => (
                          <Tag key={participant.id} color="blue" style={{ margin: 0 }}>
                            {participant.name}
                          </Tag>
                        ))}
                      </Space>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Space>
    </div>
  )
}
