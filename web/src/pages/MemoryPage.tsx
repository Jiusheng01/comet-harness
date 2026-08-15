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
  AuditOutlined,
  BulbOutlined,
  CheckCircleOutlined,
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
  type MemoryProfile,
  type ProfileEntity,
  type ReviewOverview,
} from '@/api/memories'
import ReviewPanel from '@/components/memory/ReviewPanel'

const { Text, Paragraph } = Typography

type TrustTone = 'high' | 'medium' | 'low'
type PageMode = 'memory' | 'review'
type LayerFilter = 'all' | 'long_term' | 'short_term'

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
  const navigate = useNavigate()
  const [mode, setMode] = useState<PageMode>('memory')
  const [profile, setProfile] = useState<MemoryProfile | null>(null)
  const [overview, setOverview] = useState<ReviewOverview | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(true)
  const [layer, setLayer] = useState<LayerFilter>('all')
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<MemoryHit[]>([])
  const [searching, setSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [profileRes, overviewRes, insightsRes] = await Promise.all([
        memoryApi.profile(),
        memoryApi.reviewOverview(),
        memoryApi.insights(),
      ])
      setProfile(profileRes.data)
      setOverview(overviewRes.data)
      setInsights(insightsRes.data)
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

  const filteredEntities = useMemo(() => {
    const rows = layer === 'all' ? entities : entities.filter((entity) => entity.memory_layer === layer)
    return [...rows].sort((a, b) => {
      const layerDiff = Number(b.memory_layer === 'long_term') - Number(a.memory_layer === 'long_term')
      if (layerDiff !== 0) return layerDiff
      const importanceDiff = (b.importance ?? 0) - (a.importance ?? 0)
      if (Math.abs(importanceDiff) > 0.001) return importanceDiff
      return (b.access_count + b.mention_count) - (a.access_count + a.mention_count)
    })
  }, [entities, layer])

  const total = overview?.total_entities ?? profile?.total ?? entities.length
  const longTerm = overview?.long_term ?? entities.filter((entity) => entity.memory_layer === 'long_term').length
  const shortTerm = Math.max(0, total - longTerm)
  const pending = overview?.pending ?? 0

  const onSearch = async (value?: string) => {
    const q = (value ?? query).trim()
    if (!q) {
      setHasSearched(false)
      setHits([])
      return
    }
    setQuery(q)
    setSearching(true)
    setHasSearched(true)
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
    <div className="fluid-page">
      <Card
        title="记忆"
        className="memory-card"
        extra={
          <Space wrap>
            <Segmented
              value={mode}
              onChange={(value) => setMode(value as PageMode)}
              options={[
                { label: '记忆', value: 'memory' },
                {
                  label: pending > 0 ? `审查纠错 ${pending}` : '审查纠错',
                  value: 'review',
                  icon: <AuditOutlined />,
                },
              ]}
            />
            <Button icon={<ShareAltOutlined />} onClick={() => navigate('/graph')}>
              记忆图谱
            </Button>
          </Space>
        }
      >
        {mode === 'review' ? (
          <ReviewPanel />
        ) : (
          <Space direction="vertical" size={18} style={{ width: '100%' }}>
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
                <Text strong style={{ fontSize: 16 }}>Memory Runtime</Text>
                <div>
                  <Text type="secondary" style={{ fontSize: 12.5 }}>
                    对话自动萃取记忆；这里主要看实体、短长期分层、置信度，以及实际召回结果。
                  </Text>
                </div>
              </div>
              <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
                刷新
              </Button>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
                gap: 10,
              }}
            >
              <MiniStat label="实体" value={total} />
              <MiniStat label="长期" value={longTerm} />
              <MiniStat label="短期" value={shortTerm} />
              <MiniStat label="待确认" value={pending} />
            </div>

            <Input.Search
              value={query}
              onChange={(event) => {
                const value = event.target.value
                setQuery(value)
                if (!value.trim()) {
                  setHasSearched(false)
                  setHits([])
                }
              }}
              onSearch={onSearch}
              enterButton={<><SearchOutlined /> 测试召回</>}
              loading={searching}
              allowClear
              size="large"
              placeholder="测试 Memory Retrieval，例如：我的技术方向、正在准备的面试"
            />

            {hasSearched ? (
              <RecallResults query={query} hits={hits} loading={searching} />
            ) : (
              <>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 12,
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <Text strong style={{ fontSize: 15 }}>记忆实体</Text>
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                      点击上方搜索可直接验证召回
                    </Text>
                  </div>
                  <Segmented
                    size="small"
                    value={layer}
                    onChange={(value) => setLayer(value as LayerFilter)}
                    options={[
                      { label: `全部 ${total}`, value: 'all' },
                      { label: `长期 ${longTerm}`, value: 'long_term' },
                      { label: `短期 ${shortTerm}`, value: 'short_term' },
                    ]}
                  />
                </div>

                {loading && !profile ? (
                  <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
                ) : filteredEntities.length === 0 ? (
                  <Empty description="当前没有这个层级的记忆实体" />
                ) : (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(min(19rem, 100%), 1fr))',
                      gap: 12,
                    }}
                  >
                    {filteredEntities.map((entity) => (
                      <EntityCard key={entity.id} entity={entity} />
                    ))}
                  </div>
                )}

                {insights.length > 0 && <InsightStrip insights={insights} />}
              </>
            )}
          </Space>
        )}
      </Card>
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        border: '1px solid #eef0f4',
        borderRadius: 10,
        padding: '10px 12px',
        minWidth: 0,
      }}
    >
      <Text type="secondary" style={{ fontSize: 11.5 }}>{label}</Text>
      <div style={{ fontSize: 21, lineHeight: 1.35, fontWeight: 700, color: '#171719' }}>{value}</div>
    </div>
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

function RecallResults({
  query,
  hits,
  loading,
}: {
  query: string
  hits: MemoryHit[]
  loading: boolean
}) {
  if (loading) {
    return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <div>
        <Text strong>召回结果</Text>
        <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
          query：{query}
        </Text>
      </div>
      {hits.length === 0 ? (
        <Empty description="没有达到召回阈值的记忆" />
      ) : (
        hits.map((hit) => (
          <Card key={hit.id} size="small" styles={{ body: { padding: 14 } }}>
            <Space size={5} wrap style={{ marginBottom: 6 }}>
              <Text strong>{hit.name}</Text>
              <Tag color="blue" style={{ margin: 0 }}>{hit.type}</Tag>
              <TrustTag confidence={hit.confidence} />
              <Tag color={hit.memory_layer === 'long_term' ? 'gold' : 'default'} style={{ margin: 0 }}>
                {hit.memory_layer === 'long_term' ? '长期' : '短期'}
              </Tag>
              <Tag style={{ margin: 0 }}>score {hit.score}</Tag>
            </Space>
            {hit.description && (
              <Paragraph type="secondary" style={{ margin: '2px 0 8px', fontSize: 12.5 }}>
                {hit.description}
              </Paragraph>
            )}
            {hit.relations.length > 0 && (
              <div style={{ paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
                {hit.relations.map((relation, index) => (
                  <div key={index} style={{ fontSize: 12.5, color: '#475467', lineHeight: 1.8 }}>
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
        ))
      )}
    </Space>
  )
}

function InsightStrip({ insights }: { insights: Insight[] }) {
  return (
    <div style={{ borderTop: '1px solid #f0f1f3', paddingTop: 16 }}>
      <Space size={7} style={{ marginBottom: 10 }}>
        <BulbOutlined style={{ color: '#155EEF' }} />
        <Text strong>记忆洞察</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>Reflection 派生结果</Text>
      </Space>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(min(20rem, 100%), 1fr))',
          gap: 10,
        }}
      >
        {insights.slice(0, 3).map((insight) => (
          <div
            key={insight.id}
            style={{
              border: '1px solid #eef0f4',
              borderRadius: 10,
              padding: '11px 13px',
              background: '#fafbff',
            }}
          >
            <Space size={5} wrap style={{ marginBottom: 5 }}>
              <Tag color="geekblue" style={{ margin: 0 }}>{insight.theme}</Tag>
              <TrustTag confidence={insight.confidence} />
            </Space>
            <Paragraph style={{ margin: 0, fontSize: 12.5, color: '#475467' }} ellipsis={{ rows: 2 }}>
              {insight.content}
            </Paragraph>
          </div>
        ))}
      </div>
    </div>
  )
}
