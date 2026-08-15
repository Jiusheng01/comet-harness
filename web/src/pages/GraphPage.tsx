import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Button, Card, Empty, Input, Segmented, Space, Spin, Tag, Typography, message } from 'antd'
import {
  AimOutlined,
  MergeCellsOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { memoryApi, type GraphData, type GraphEdge, type GraphNode } from '@/api/memories'

const { Text, Paragraph } = Typography

type Kind = 'Entity' | 'Event' | 'Statement' | 'Chunk' | 'Dialogue'
type GraphView = 'entity' | 'event' | 'provenance'

const KIND_META: Record<Kind, { label: string; color: string }> = {
  Entity: { label: '实体', color: '#155EEF' },
  Event: { label: '事件', color: '#FA8C16' },
  Statement: { label: '陈述', color: '#7B61FF' },
  Chunk: { label: '文本块', color: '#69B1FF' },
  Dialogue: { label: '对话', color: '#13A8A8' },
}

const REL_LABEL: Record<string, string> = {
  RELATION: '语义关系',
  INVOLVES: '涉及',
  MENTIONS: '提及',
  HAS_STATEMENT: '包含陈述',
  HAS_CHUNK: '包含文本块',
}

interface FGNode extends GraphNode {
  x?: number
  y?: number
  fx?: number
  fy?: number
}

interface FGLink {
  source: string | FGNode
  target: string | FGNode
  rel?: string
  predicate?: string
  predicate_surface?: string
}

interface RelationDetail {
  label: string
  source: GraphNode
  target: GraphNode
}

interface ProvenanceDetail {
  label: string
  source: GraphNode
  target: GraphNode
}

function kindOf(node: GraphNode): Kind {
  const kind = node.kind as Kind | undefined
  return kind && kind in KIND_META ? kind : 'Entity'
}

function linkId(value: string | FGNode) {
  return typeof value === 'string' ? value : value.id
}

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const listener = (event: MediaQueryListEvent) => setMobile(event.matches)
    mq.addEventListener('change', listener)
    return () => mq.removeEventListener('change', listener)
  }, [])
  return mobile
}

function viewAllowsNode(view: GraphView, node: GraphNode) {
  const kind = kindOf(node)
  if (view === 'entity') return kind === 'Entity'
  if (view === 'event') return kind === 'Entity' || kind === 'Event'
  return kind === 'Dialogue' || kind === 'Chunk' || kind === 'Statement' || kind === 'Entity'
}

function viewAllowsEdge(view: GraphView, edge: GraphEdge) {
  if (view === 'entity') return edge.rel === 'RELATION'
  if (view === 'event') return edge.rel === 'INVOLVES'
  return edge.rel === 'HAS_CHUNK' || edge.rel === 'HAS_STATEMENT' || edge.rel === 'MENTIONS'
}

export default function GraphPage() {
  const isMobile = useIsMobile()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<GraphData | null>(null)
  const [view, setView] = useState<GraphView>('entity')
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [shownIds, setShownIds] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [merging, setMerging] = useState(false)

  const wrapRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<ForceGraphMethods<FGNode, FGLink> | undefined>(undefined)
  const [size, setSize] = useState({ w: 900, h: 520 })
  const highlightNodes = useRef<Set<string>>(new Set())
  const highlightLinks = useRef<Set<FGLink>>(new Set())
  const [, repaint] = useState(0)

  const load = useCallback((showLoading = true) => {
    if (showLoading) setLoading(true)
    memoryApi
      .graph()
      .then(({ data }) => setData(data))
      .catch((error) => message.error((error as Error).message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const element = wrapRef.current
    if (!element) return
    const update = () => setSize({ w: element.clientWidth || 900, h: element.clientHeight || 520 })
    update()
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [data, view])

  const store = useMemo(() => {
    const nodeMap = new Map<string, GraphNode>()
    const fgNodes = new Map<string, FGNode>()
    data?.nodes.forEach((node) => {
      nodeMap.set(node.id, node)
      fgNodes.set(node.id, { ...node })
    })
    return { nodeMap, fgNodes }
  }, [data])

  const viewStore = useMemo(() => {
    const candidates = new Set<string>()
    data?.nodes.forEach((node) => {
      if (viewAllowsNode(view, node)) candidates.add(node.id)
    })

    const allowedEdges = (data?.edges ?? []).filter(
      (edge) => viewAllowsEdge(view, edge) && candidates.has(edge.source) && candidates.has(edge.target),
    )

    // 事件视图只保留真正参与事件的 Entity/Event，避免没有事件时仍显示孤立实体。
    const eligible = view === 'event'
      ? new Set(allowedEdges.flatMap((edge) => [edge.source, edge.target]))
      : candidates

    const adj = new Map<string, Set<string>>()
    const degree = new Map<string, number>()
    eligible.forEach((id) => {
      adj.set(id, new Set())
      degree.set(id, 0)
    })

    const edges: GraphEdge[] = []
    allowedEdges.forEach((edge) => {
      if (!eligible.has(edge.source) || !eligible.has(edge.target)) return
      edges.push(edge)
      adj.get(edge.source)?.add(edge.target)
      adj.get(edge.target)?.add(edge.source)
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1)
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1)
    })

    return { eligible, adj, degree, edges }
  }, [data, view])

  const chooseSeed = useCallback(() => {
    if (!data) return null
    const nodes = data.nodes.filter((node) => viewStore.eligible.has(node.id))
    if (!nodes.length) return null
    const entities = nodes.filter((node) => kindOf(node) === 'Entity')
    const pool = entities.length ? entities : nodes
    return (
      pool.find((node) => /用户|^我$|本人|自己/.test(node.name)) ??
      pool.reduce((best, node) =>
        (viewStore.degree.get(node.id) ?? 0) > (viewStore.degree.get(best.id) ?? 0) ? node : best,
      )
    )
  }, [data, viewStore])

  const resetFocus = useCallback(() => {
    const seed = chooseSeed()
    if (!seed) {
      setShownIds(new Set())
      setSelected(null)
      return
    }

    const ids = new Set<string>([seed.id])
    let frontier = [seed.id]
    const hops = view === 'provenance' ? 3 : 1
    for (let hop = 0; hop < hops; hop += 1) {
      const next: string[] = []
      frontier.forEach((id) => {
        viewStore.adj.get(id)?.forEach((neighbor) => {
          if (ids.has(neighbor)) return
          ids.add(neighbor)
          next.push(neighbor)
        })
      })
      frontier = next
    }

    setShownIds(ids)
    setSelected(seed)
    setTimeout(() => fgRef.current?.zoomToFit(500, 70), 350)
  }, [chooseSeed, view, viewStore])

  useEffect(() => {
    resetFocus()
  }, [resetFocus])

  const expand = useCallback((id: string) => {
    setShownIds((previous) => {
      const next = new Set(previous)
      next.add(id)
      viewStore.adj.get(id)?.forEach((neighbor) => next.add(neighbor))
      return next
    })
  }, [viewStore])

  const graphData = useMemo(() => {
    const nodes: FGNode[] = []
    shownIds.forEach((id) => {
      if (!viewStore.eligible.has(id)) return
      const node = store.fgNodes.get(id)
      if (node) nodes.push(node)
    })
    const visible = new Set(nodes.map((node) => node.id))
    const links: FGLink[] = viewStore.edges
      .filter((edge) => visible.has(edge.source) && visible.has(edge.target))
      .map((edge) => ({
        source: edge.source,
        target: edge.target,
        rel: edge.rel,
        predicate: edge.predicate,
        predicate_surface: edge.predicate_surface,
      }))
    return { nodes, links }
  }, [shownIds, store, viewStore])

  useEffect(() => {
    const graph = fgRef.current
    if (!graph) return
    const count = graphData.nodes.length
    graph.d3Force('charge')?.strength(count > 50 ? -420 : count > 20 ? -320 : -240)
    graph.d3Force('link')?.distance(view === 'provenance' ? 65 : 90)
    graph.d3ReheatSimulation()
  }, [graphData, view])

  const maxDegree = useMemo(
    () => Math.max(1, ...Array.from(viewStore.degree.values())),
    [viewStore],
  )

  const nodeRadius = useCallback((node: FGNode) => {
    const kind = kindOf(node)
    const mobileScale = isMobile ? 1.35 : 1
    if (kind === 'Entity') {
      const degree = viewStore.degree.get(node.id) ?? 0
      const importance = typeof node.importance === 'number' ? node.importance : 0.5
      return Math.min(12, 5 + (degree / maxDegree) * 5 + importance * 2) * mobileScale
    }
    if (kind === 'Event') return 6 * mobileScale
    if (kind === 'Statement') return 4.5 * mobileScale
    return 3.8 * mobileScale
  }, [isMobile, maxDegree, viewStore])

  const onNodeHover = useCallback((node: FGNode | null) => {
    highlightNodes.current.clear()
    highlightLinks.current.clear()
    if (node) {
      highlightNodes.current.add(node.id)
      graphData.links.forEach((link) => {
        if (linkId(link.source) === node.id || linkId(link.target) === node.id) {
          highlightLinks.current.add(link)
          highlightNodes.current.add(linkId(link.source))
          highlightNodes.current.add(linkId(link.target))
        }
      })
    }
    repaint((value) => value + 1)
  }, [graphData])

  const onNodeClick = useCallback((node: FGNode) => {
    expand(node.id)
    setSelected(store.nodeMap.get(node.id) ?? node)
  }, [expand, store])

  const onNodeDragEnd = useCallback((node: FGNode) => {
    node.fx = node.x
    node.fy = node.y
  }, [])

  const doSearch = useCallback((query: string) => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return
    const hit = Array.from(store.fgNodes.values()).find(
      (node) => viewStore.eligible.has(node.id) && node.name.toLowerCase().includes(keyword),
    )
    if (!hit) {
      message.info('当前视图没有找到匹配节点')
      return
    }
    const ids = new Set<string>([hit.id])
    viewStore.adj.get(hit.id)?.forEach((neighbor) => ids.add(neighbor))
    setShownIds((previous) => new Set([...previous, ...ids]))
    setSelected(store.nodeMap.get(hit.id) ?? hit)
    setTimeout(() => {
      if (hit.x != null && hit.y != null) fgRef.current?.centerAt(hit.x, hit.y, 500)
      fgRef.current?.zoom(2.1, 500)
    }, 250)
  }, [store, viewStore])

  const onMergeDuplicates = async () => {
    setMerging(true)
    try {
      const { data } = await memoryApi.mergeDuplicates()
      message.success(`已合并 ${data.removed} 个重复实体`)
      load(false)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setMerging(false)
    }
  }

  const clearPinsAndReset = () => {
    store.fgNodes.forEach((node) => {
      node.fx = undefined
      node.fy = undefined
    })
    resetFocus()
  }

  const counts = useMemo(() => {
    const result: Record<Kind, number> = {
      Entity: 0,
      Event: 0,
      Statement: 0,
      Chunk: 0,
      Dialogue: 0,
    }
    data?.nodes.forEach((node) => {
      result[kindOf(node)] += 1
    })
    return result
  }, [data])

  const detail = useMemo(() => {
    if (!data || !selected) {
      return { relations: [], statements: [], events: [], participants: [], provenance: [] }
    }

    const relations: RelationDetail[] = []
    const statements: GraphNode[] = []
    const events: GraphNode[] = []
    const participants: GraphNode[] = []
    const provenance: ProvenanceDetail[] = []

    data.edges.forEach((edge) => {
      if (edge.source !== selected.id && edge.target !== selected.id) return
      const source = store.nodeMap.get(edge.source)
      const target = store.nodeMap.get(edge.target)
      if (!source || !target) return
      const other = edge.source === selected.id ? target : source

      if (edge.rel === 'RELATION') {
        relations.push({
          label: edge.predicate_surface || edge.predicate || '关联',
          source,
          target,
        })
      } else if (edge.rel === 'MENTIONS') {
        if (kindOf(other) === 'Statement') statements.push(other)
        provenance.push({ label: REL_LABEL.MENTIONS, source, target })
      } else if (edge.rel === 'INVOLVES') {
        if (kindOf(other) === 'Event') events.push(other)
        if (kindOf(other) === 'Entity') participants.push(other)
      } else if (edge.rel === 'HAS_CHUNK' || edge.rel === 'HAS_STATEMENT') {
        provenance.push({ label: REL_LABEL[edge.rel], source, target })
      }
    })

    return { relations, statements, events, participants, provenance }
  }, [data, selected, store])

  const viewHelp =
    view === 'entity'
      ? '系统记住了什么：只展示实体与语义关系。'
      : view === 'event'
        ? '发生过什么：只展示事件与参与实体，不混入普通语义关系。'
        : '为什么记住：只展示 Dialogue → Chunk → Statement → Entity 的来源链路。'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Card
        title={isMobile ? undefined : '记忆图谱'}
        style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
        styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 } }}
        extra={
          <Space wrap size={6}>
            <Segmented
              size="small"
              value={view}
              onChange={(value) => setView(value as GraphView)}
              options={[
                { label: '实体视图', value: 'entity' },
                { label: '事件视图', value: 'event' },
                { label: '溯源视图', value: 'provenance' },
              ]}
            />
            <Input.Search
              size="small"
              allowClear
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onSearch={doSearch}
              placeholder="搜索节点"
              style={{ width: isMobile ? 130 : 180 }}
            />
            <Button size="small" icon={<AimOutlined />} onClick={() => fgRef.current?.zoomToFit(500, 70)}>
              {isMobile ? '' : '居中'}
            </Button>
            <Button size="small" icon={<MergeCellsOutlined />} loading={merging} onClick={onMergeDuplicates}>
              {isMobile ? '' : '合并重复'}
            </Button>
            <Button size="small" icon={<ReloadOutlined />} onClick={clearPinsAndReset}>
              {isMobile ? '' : '重置视图'}
            </Button>
          </Space>
        }
      >
        <div
          ref={wrapRef}
          style={{ position: 'relative', height: isMobile ? '32rem' : 'min(58vh, 37rem)', minHeight: '28rem', overflow: 'hidden' }}
        >
          {loading ? (
            <div style={center}><Spin /></div>
          ) : !data || data.nodes.length === 0 ? (
            <div style={center}><Empty description="还没有记忆图谱数据" /></div>
          ) : graphData.nodes.length === 0 ? (
            <div style={center}>
              <Empty description={view === 'event' ? '当前还没有事件记忆' : '当前视图暂时没有可展示的节点'} />
            </div>
          ) : (
            <>
              <ForceGraph2D
                ref={fgRef}
                graphData={graphData}
                width={size.w}
                height={size.h}
                nodeId="id"
                cooldownTicks={120}
                d3VelocityDecay={0.3}
                linkColor={(link) =>
                  highlightLinks.current.has(link as FGLink)
                    ? '#155EEF'
                    : (link as FGLink).rel === 'RELATION'
                      ? 'rgba(107,119,140,0.58)'
                      : 'rgba(170,180,195,0.42)'
                }
                linkWidth={(link) => (highlightLinks.current.has(link as FGLink) ? 2.4 : 1)}
                linkDirectionalArrowLength={(link) => (link as FGLink).rel === 'RELATION' ? 4 : 2.5}
                linkDirectionalArrowRelPos={1}
                linkLabel={(link) => {
                  const item = link as FGLink
                  return item.predicate_surface || item.predicate || REL_LABEL[item.rel ?? ''] || ''
                }}
                onNodeHover={(node) => onNodeHover(node as FGNode | null)}
                onNodeClick={(node) => onNodeClick(node as FGNode)}
                onNodeDragEnd={(node) => onNodeDragEnd(node as FGNode)}
                nodeCanvasObject={(rawNode, ctx, globalScale) => {
                  const node = rawNode as FGNode
                  const radius = nodeRadius(node)
                  const kind = kindOf(node)
                  const dimmed = highlightNodes.current.size > 0 && !highlightNodes.current.has(node.id)
                  ctx.globalAlpha = dimmed ? 0.18 : 1
                  ctx.beginPath()
                  ctx.arc(node.x!, node.y!, radius, 0, Math.PI * 2)
                  ctx.fillStyle = KIND_META[kind].color
                  ctx.fill()
                  if (selected?.id === node.id) {
                    ctx.lineWidth = 2 / globalScale
                    ctx.strokeStyle = '#101828'
                    ctx.stroke()
                  }
                  if (globalScale > 0.7 || radius >= 8) {
                    const label = node.name.length > 13 ? `${node.name.slice(0, 13)}…` : node.name
                    const fontSize = Math.max(3.3, 11 / globalScale)
                    ctx.font = `${fontSize}px -apple-system, "PingFang SC", sans-serif`
                    ctx.textAlign = 'center'
                    ctx.textBaseline = 'top'
                    ctx.fillStyle = dimmed ? 'rgba(29,33,41,0.24)' : '#1D2129'
                    ctx.fillText(label, node.x!, node.y! + radius + 2)
                  }
                  ctx.globalAlpha = 1
                }}
                nodePointerAreaPaint={(rawNode, color, ctx) => {
                  const node = rawNode as FGNode
                  ctx.fillStyle = color
                  ctx.beginPath()
                  ctx.arc(node.x!, node.y!, nodeRadius(node) + (isMobile ? 6 : 3), 0, Math.PI * 2)
                  ctx.fill()
                }}
              />

              <div style={hintPanel}>
                <Text strong style={{ fontSize: 12 }}>{viewHelp}</Text>
                <div style={{ marginTop: 4, fontSize: 11.5, color: '#667085' }}>
                  当前展开 {graphData.nodes.length} 个节点 / {graphData.links.length} 条边
                </div>
              </div>

              <div style={legendPanel}>
                <Text strong style={{ fontSize: 12 }}>节点类型</Text>
                <LegendRow color={KIND_META.Entity.color} label={`实体 ${counts.Entity}`} />
                {view === 'event' && <LegendRow color={KIND_META.Event.color} label={`事件 ${counts.Event}`} />}
                {view === 'provenance' && (
                  <>
                    <LegendRow color={KIND_META.Statement.color} label={`陈述 ${counts.Statement}`} />
                    <LegendRow color={KIND_META.Chunk.color} label={`文本块 ${counts.Chunk}`} />
                    <LegendRow color={KIND_META.Dialogue.color} label={`对话 ${counts.Dialogue}`} />
                  </>
                )}
                {data.communities.length > 0 && view === 'entity' && (
                  <div style={{ marginTop: 9, paddingTop: 8, borderTop: '1px solid #f0f1f3' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>社区 {data.communities.length} 个</Text>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <NodeDetail
          view={view}
          node={selected}
          detail={detail}
          onOpenProvenance={() => setView('provenance')}
        />
      </Card>
    </div>
  )
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 7, fontSize: 11.5, color: '#475467' }}>
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: color, display: 'inline-block' }} />
      {label}
    </div>
  )
}

function NodeDetail({
  view,
  node,
  detail,
  onOpenProvenance,
}: {
  view: GraphView
  node: GraphNode | null
  detail: {
    relations: RelationDetail[]
    statements: GraphNode[]
    events: GraphNode[]
    participants: GraphNode[]
    provenance: ProvenanceDetail[]
  }
  onOpenProvenance: () => void
}) {
  if (!node) {
    const hint = view === 'entity'
      ? '点击实体查看语义关系和来源陈述。'
      : view === 'event'
        ? '点击事件或实体查看参与关系。'
        : '点击来源链路中的节点查看上下游来源。'
    return (
      <div style={{ padding: '14px 18px', borderTop: '1px solid #eef0f4', background: '#fff' }}>
        <Text type="secondary">{hint}</Text>
      </div>
    )
  }

  const kind = kindOf(node)

  const context = view === 'entity' ? (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
      <DetailColumn title={`相关关系 (${detail.relations.length})`}>
        {detail.relations.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>暂无语义关系</Text>
        ) : detail.relations.slice(0, 8).map((item, index) => (
          <div key={`${item.source.id}-${item.target.id}-${index}`} style={detailRow}>
            <Text>{item.source.name}</Text> <Text type="secondary">— {item.label} →</Text> <Text>{item.target.name}</Text>
          </div>
        ))}
      </DetailColumn>

      <DetailColumn title={`来源陈述 (${detail.statements.length})`}>
        {detail.statements.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>暂无直接来源陈述</Text>
        ) : (
          <>
            {detail.statements.slice(0, 4).map((statement) => (
              <div key={statement.id} style={detailRow}>{statement.name || statement.description}</div>
            ))}
            <Button type="link" size="small" style={{ paddingLeft: 0 }} onClick={onOpenProvenance}>
              查看完整溯源 →
            </Button>
          </>
        )}
      </DetailColumn>
    </div>
  ) : view === 'event' ? (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 10 }}>
      {kind === 'Event' ? (
        <DetailColumn title={`参与实体 (${detail.participants.length})`}>
          {detail.participants.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 12 }}>暂无参与实体</Text>
          ) : detail.participants.slice(0, 8).map((participant) => (
            <div key={participant.id} style={detailRow}>{participant.name}</div>
          ))}
        </DetailColumn>
      ) : (
        <DetailColumn title={`相关事件 (${detail.events.length})`}>
          {detail.events.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 12 }}>暂无关联事件</Text>
          ) : detail.events.slice(0, 8).map((event) => (
            <div key={event.id} style={detailRow}>{event.name}</div>
          ))}
        </DetailColumn>
      )}
    </div>
  ) : (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 10 }}>
      <DetailColumn title={`来源链路 (${detail.provenance.length})`}>
        {detail.provenance.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>当前节点没有更多来源链路</Text>
        ) : detail.provenance.slice(0, 10).map((item, index) => (
          <div key={`${item.source.id}-${item.target.id}-${index}`} style={detailRow}>
            <Text>{item.source.name}</Text> <Text type="secondary">— {item.label} →</Text> <Text>{item.target.name}</Text>
          </div>
        ))}
      </DetailColumn>
    </div>
  )

  return (
    <div
      style={{
        borderTop: '1px solid #eef0f4',
        background: '#fff',
        padding: '14px 18px 16px',
        display: 'grid',
        gridTemplateColumns: 'minmax(240px, 0.8fr) minmax(300px, 1.2fr)',
        gap: 18,
      }}
    >
      <div>
        <Space size={6} wrap>
          <Text strong style={{ fontSize: 15 }}>节点详情：{node.name}</Text>
          <Tag color="blue" style={{ margin: 0 }}>{KIND_META[kind].label}</Tag>
          {node.memory_layer && (
            <Tag color={node.memory_layer === 'long_term' ? 'green' : 'default'} style={{ margin: 0 }}>
              {node.memory_layer === 'long_term' ? '长期记忆' : '短期记忆'}
            </Tag>
          )}
        </Space>
        {node.description && (
          <Paragraph type="secondary" style={{ margin: '8px 0', fontSize: 12.5 }} ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
            {node.description}
          </Paragraph>
        )}
        <Space size={5} wrap>
          {typeof node.importance === 'number' && <Tag>重要度 {node.importance.toFixed(2)}</Tag>}
          {node.community_id && view === 'entity' && <Tag color="purple">社区 {node.community_id.slice(0, 8)}</Tag>}
          {kind === 'Entity' && <Tag>被提及 {node.mention_count ?? 0}</Tag>}
          {kind === 'Entity' && <Tag>被召回 {node.access_count ?? 0}</Tag>}
        </Space>
        {node.core_facts && node.core_facts.length > 0 && view === 'entity' && (
          <div style={{ marginTop: 9 }}>
            {node.core_facts.slice(0, 4).map((fact) => (
              <div key={fact} style={{ color: '#155EEF', fontSize: 12.5, lineHeight: 1.75 }}>✦ {fact}</div>
            ))}
          </div>
        )}
      </div>

      {context}
    </div>
  )
}

function DetailColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ minWidth: 0, borderLeft: '1px solid #f0f1f3', paddingLeft: 12 }}>
      <Text strong style={{ fontSize: 12.5 }}>{title}</Text>
      <div style={{ marginTop: 7 }}>{children}</div>
    </div>
  )
}

const center: CSSProperties = {
  height: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const hintPanel: CSSProperties = {
  position: 'absolute',
  top: 14,
  left: 14,
  maxWidth: '55%',
  padding: '8px 10px',
  borderRadius: 8,
  background: 'rgba(255,255,255,0.92)',
  border: '1px solid rgba(234,236,240,0.9)',
  pointerEvents: 'none',
}

const legendPanel: CSSProperties = {
  position: 'absolute',
  top: 14,
  right: 14,
  minWidth: 126,
  padding: '10px 12px',
  borderRadius: 9,
  background: 'rgba(255,255,255,0.94)',
  border: '1px solid #eef0f4',
  boxShadow: '0 3px 14px rgba(16,24,40,0.06)',
}

const detailRow: CSSProperties = {
  fontSize: 12,
  color: '#475467',
  lineHeight: 1.65,
  marginBottom: 5,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}
