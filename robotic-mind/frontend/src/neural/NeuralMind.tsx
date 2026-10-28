import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, ArrowUpRight, Brain, ChevronRight, Crosshair, Eye, Fingerprint, Maximize2, Minus, Network, Pause, Play, Plus, Search, Sparkles, X } from 'lucide-react'
import { api } from '../api'
import type { Snapshot } from '../types'
import { colors, connectionPath, hash, names, placeNodes } from './graph'
import type { MindGraph, MindNode, NodeKind } from './graph'
import './neural.css'

const hemispheres = 'M486 113 C450 72 410 92 395 96 C370 63 325 84 310 109 C268 93 233 120 229 147 C184 144 155 182 165 219 C122 240 123 288 145 308 C111 348 128 391 159 405 C147 449 180 486 214 485 C228 526 264 545 305 532 C329 568 375 573 404 548 C443 564 479 538 486 500 Z'
const legend: NodeKind[] = ['robot', 'discovery', 'memory', 'observation', 'mission', 'region']
const filters = [{ id: 'all', label: 'All connections' }, { id: 'discovery', label: 'Discoveries' }, { id: 'memory', label: 'Memories' }, { id: 'mission', label: 'Missions' }]
const timestamp = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function NeuralMind({ spaceId, data, connected }: { spaceId: string; data: Snapshot; connected: boolean }) {
  const [graph, setGraph] = useState<MindGraph | null>(null)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [hovered, setHovered] = useState('')
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [animate, setAnimate] = useState(!window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [labels, setLabels] = useState(false)
  const [camera, setCamera] = useState({ x: 0, y: 0, scale: 1 })
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const ready = graph !== null

  useEffect(() => {
    let stopped = false
    async function load() {
      try {
        const result = await api<MindGraph>(`/spaces/${spaceId}/mind/graph`)
        if (!stopped) { setGraph(result); setError('') }
      } catch (e) { if (!stopped) setError((e as Error).message) }
    }
    setGraph(null); setSelectedId(''); setCamera({ x: 0, y: 0, scale: 1 })
    load()
    const interval = setInterval(load, 2000)
    return () => { stopped = true; clearInterval(interval) }
  }, [spaceId])

  const zoom = useCallback((factor: number) => setCamera(c => ({ ...c, scale: Math.max(.55, Math.min(2.6, c.scale * factor)) })), [])
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const wheel = (event: WheelEvent) => { event.preventDefault(); zoom(event.deltaY < 0 ? 1.08 : 1 / 1.08) }
    svg.addEventListener('wheel', wheel, { passive: false })
    return () => svg.removeEventListener('wheel', wheel)
  }, [ready, zoom])

  const placed = useMemo(() => placeNodes(graph?.nodes || []), [graph?.nodes])
  const byId = useMemo(() => new Map(placed.map(n => [n.id, n])), [placed])
  const rootId = `group:${spaceId}`
  const selected = byId.get(selectedId) || byId.get(rootId)
  const focusId = hovered || selectedId
  const related = useMemo(() => {
    const set = new Set([focusId])
    for (const e of graph?.edges || []) { if (e.source === focusId) set.add(e.target); if (e.target === focusId) set.add(e.source) }
    return set
  }, [graph?.edges, focusId])
  const matching = useMemo(() => new Set(placed.filter(n => {
    const type = filter === 'all' || n.kind === filter
    const query = !search || `${n.label} ${n.summary} ${n.owner_id || ''}`.toLowerCase().includes(search.toLowerCase())
    return type && query
  }).map(n => n.id)), [placed, filter, search])
  const filtering = filter !== 'all' || Boolean(search)
  const connections = (graph?.edges || []).filter(e => e.source === selected?.id || e.target === selected?.id)
  const recent = (n: MindNode) => Boolean(n.timestamp && Date.now() - Date.parse(n.timestamp) < 15000)
  const liveEdges = (graph?.edges || []).filter(e => {
    const a = byId.get(e.source), b = byId.get(e.target)
    return a && b && (recent(b) || (e.relation === 'executes' && b.status === 'started'))
  })
  const activeEdgeIds = new Set(liveEdges.map(e => e.id))
  const mission = data.missions.at(-1)
  const activeMission = mission && !['complete', 'failed'].includes(mission.state)
  const ownerName = (id: string | null) => data.members.find(m => m.id === id)?.display_name || id || 'Shared space'
  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest('[data-neuron]')) return
    drag.current = { x: event.clientX, y: event.clientY, originX: camera.x, originY: camera.y }
    event.currentTarget.setPointerCapture(event.pointerId); setDragging(true)
  }
  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return
    const bounds = event.currentTarget.getBoundingClientRect()
    const ratio = Math.min(bounds.width / 1000, bounds.height / 640)
    setCamera(c => ({ ...c, x: drag.current!.originX + (event.clientX - drag.current!.x) / ratio, y: drag.current!.originY + (event.clientY - drag.current!.y) / ratio }))
  }
  const release = () => { drag.current = null; setDragging(false) }

  return <section className={`neural-mind ${animate ? '' : 'neural-paused'}`} aria-label="Group Mind neural network">
    <div className="neural-heading"><div className="neural-heading-icon"><Brain size={23}/></div><div><div className="neural-eyebrow">COLLECTIVE INTELLIGENCE</div><h1>Group Mind</h1><p>A mind made of many. Every discovery strengthens the whole.</p></div><div className="neural-live"><i className={connected ? 'neural-status-dot' : 'neural-status-dot offline'}/>{connected ? 'LIVE NETWORK' : 'RECONNECTING'}<small>{data.ai.mode === 'nebius' ? 'NVIDIA NEMOTRON' : 'DEVELOPMENT MOCK'}</small></div></div>
    <div className="neural-stats"><div><span>NEURONS</span><strong>{graph?.nodes.length.toString().padStart(3, '0') || '—'}</strong><small>persisted entities</small></div><div><span>CONNECTIONS</span><strong>{graph?.edges.length.toString().padStart(3, '0') || '—'}</strong><small>traceable relationships</small></div><div><span>SHARED DISCOVERIES</span><strong>{(graph?.counts.discovery || 0).toString().padStart(2, '0')}</strong><small>collective knowledge</small></div><div><span>CONNECTED MINDS</span><strong>{data.members.filter(m => m.member_type === 'robot' && m.status === 'online').length}<em> / {data.members.filter(m => m.member_type === 'robot').length}</em></strong><small>robots online</small></div></div>
    <div className="neural-workbench"><div className="neural-canvas-column">
      <div className="neural-toolbar"><div className="neural-filters" role="group" aria-label="Filter neurons">{filters.map(f => <button key={f.id} aria-pressed={filter === f.id} className={filter === f.id ? 'active' : ''} onClick={() => setFilter(f.id)}>{f.label}</button>)}</div><label className="neural-search"><Search size={13}/><input aria-label="Search neural network" value={search} onChange={e => setSearch(e.target.value)} placeholder="Find a thought…"/>{search && <button onClick={() => setSearch('')} aria-label="Clear neural search"><X size={11}/></button>}</label></div>
      <div className={`neural-stage ${dragging ? 'dragging' : ''}`}>
        <div className="neural-stage-top"><span><Network size={12}/> SHARED COGNITIVE GRAPH</span><span>{filtering ? `${matching.size} MATCHING NEURONS` : activeMission ? 'MISSION IN PROGRESS' : 'PERSISTENT MEMORY'}</span></div>
        {error && <div className="neural-error" role="alert">{error}<small>Retrying automatically…</small></div>}
        {!graph && !error && <div className="neural-loading"><Brain size={38}/><span>Reconstructing shared memory…</span></div>}
        {graph && <svg ref={svgRef} className="neural-svg" viewBox="0 0 1000 640" aria-label={`${graph.nodes.length} neurons and ${graph.edges.length} evidence connections`} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={release} onPointerCancel={release}>
          <defs>
            <radialGradient id="neural-atmosphere"><stop offset="0" stopColor="#5963ad" stopOpacity=".13"/><stop offset="1" stopColor="#070d18" stopOpacity="0"/></radialGradient>
            <linearGradient id="hemisphere-fill" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#426ca9" stopOpacity=".055"/><stop offset="1" stopColor="#8d65bb" stopOpacity=".035"/></linearGradient>
            <filter id="neuron-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="4"/></filter>
            <pattern id="neural-dots" width="25" height="25" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".65" fill="#a7b6da" opacity=".15"/></pattern>
          </defs>
          <rect width="1000" height="640" fill="url(#neural-dots)"/><ellipse cx="500" cy="325" rx="460" ry="300" fill="url(#neural-atmosphere)"/>
          <g transform={`translate(${500 + camera.x} ${320 + camera.y}) scale(${camera.scale}) translate(-500 -320)`}>
            <g className="brain-contour"><path d={hemispheres}/><path d={hemispheres} transform="translate(1000 0) scale(-1 1)"/><path d="M489 126 Q481 215 493 275 M508 380 Q516 453 506 514" className="brain-fissure"/></g>
            <g className="neural-connections">{graph.edges.map(e => {
              const a = byId.get(e.source), b = byId.get(e.target)
              if (!a || !b) return null
              const focused = Boolean(focusId && (e.source === focusId || e.target === focusId))
              const dim = focusId ? !focused : filtering && !matching.has(e.source) && !matching.has(e.target)
              const path = connectionPath(a, b, e.id)
              const active = activeEdgeIds.has(e.id)
              return <g key={e.id} className={`synapse ${focused ? 'focused' : ''} ${dim ? 'dim' : ''} ${active ? 'active-synapse' : ''}`}><path d={path} stroke={colors[b.kind]} strokeWidth={focused ? 1.3 : .65}/>{active && animate && <circle r="2" fill={colors[b.kind]}><animateMotion path={path} dur={`${2 + hash(e.id) % 20 / 10}s`} repeatCount="indefinite"/></circle>}</g>
            })}</g>
            <g>{placed.map(n => {
              const dim = Boolean(focusId && !related.has(n.id)) || Boolean(filtering && !matching.has(n.id) && n.kind !== 'group')
              const chosen = selected?.id === n.id
              const showLabel = labels || chosen || ['group', 'robot', 'human', 'discovery', 'region'].includes(n.kind)
              return <g key={n.id} data-neuron={n.id} role="button" tabIndex={0} aria-label={`${names[n.kind]}: ${n.label}`} aria-pressed={chosen} className={`neuron ${dim ? 'dim' : ''} ${chosen ? 'selected' : ''} ${recent(n) ? 'new-evidence' : ''}`} transform={`translate(${n.x} ${n.y})`} onMouseEnter={() => setHovered(n.id)} onMouseLeave={() => setHovered('')} onClick={() => setSelectedId(n.kind === 'group' || selectedId === n.id ? '' : n.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedId(n.kind === 'group' || selectedId === n.id ? '' : n.id) } }} style={{ '--neuron-color': colors[n.kind] } as React.CSSProperties}>
                <title>{n.label} · {names[n.kind]}{n.shared ? ' · shared' : ''}</title>
                <circle className="neuron-hit" r={Math.max(12, n.radius + 5)}/>
                <circle className="neuron-aura" r={n.radius * 2.3} fill={colors[n.kind]} filter="url(#neuron-glow)"/>
                {[0, 1, 2].map(i => { const a = i * 2.094 + hash(n.id) % 10; return <path key={i} d={`M${Math.cos(a) * n.radius} ${Math.sin(a) * n.radius} l${Math.cos(a) * 9} ${Math.sin(a) * 9} m${-Math.cos(a) * 3} ${-Math.sin(a) * 3} l${Math.cos(a + 1) * 4} ${Math.sin(a + 1) * 4}`} className="dendrite"/> })}
                {chosen && <circle r={n.radius + 9} className="neuron-selection"/>}
                {recent(n) && <circle r={n.radius + 5} className="neuron-pulse"/>}
                <circle className="neuron-body" r={n.radius}/><circle r={n.radius * .35} fill="#edf4ff" opacity=".9"/>
                {showLabel && <text className={`neuron-label ${n.kind === 'group' ? 'group-label' : ''}`} y={n.radius + (n.kind === 'group' ? 27 : 18)} textAnchor="middle">{n.label.length > 28 ? n.label.slice(0, 26) + '…' : n.label}</text>}
                {n.kind === 'group' && <text className="group-sublabel" y={n.radius + 43} textAnchor="middle">{graph.counts.memory || 0} MEMORIES · ONE SHARED SPACE</text>}
              </g>
            })}</g>
          </g>
        </svg>}
        <div className="neural-stage-bottom"><span><span className={liveEdges.length ? 'neural-status-dot' : 'neural-idle-dot'}/>{liveEdges.length ? `${liveEdges.length} ACTIVE SIGNAL PATHS` : 'MEMORY RETAINED · AWAITING NEW ACTIVITY'}</span><div className="neural-map-controls"><button aria-label={animate ? 'Pause signal animation' : 'Play signal animation'} title={animate ? 'Pause animation' : 'Play animation'} onClick={() => setAnimate(!animate)}>{animate ? <Pause size={13}/> : <Play size={13}/>}</button><button aria-label="Zoom out neural network" onClick={() => zoom(1 / 1.2)}><Minus size={14}/></button><span>{Math.round(camera.scale * 100)}%</span><button aria-label="Zoom in neural network" onClick={() => zoom(1.2)}><Plus size={14}/></button><button aria-label="Reset neural view" title="Fit network" onClick={() => setCamera({ x: 0, y: 0, scale: 1 })}><Maximize2 size={13}/></button></div></div>
      </div>
      <div className="neural-legend">{legend.map(kind => <span key={kind}><i style={{ background: colors[kind] }}/>{names[kind]}</span>)}<button aria-pressed={labels} onClick={() => setLabels(!labels)}><Eye size={12}/>{labels ? 'Fewer labels' : 'Show labels'}</button></div>
      <div className="neural-caption"><Fingerprint size={13}/><span>Every neuron and connection comes from workspace records. Select one to trace its evidence.</span>{graph?.truncated && <strong>Showing {graph.nodes.length} of {graph.total_nodes} neurons.</strong>}</div>
    </div>
    <aside className="neural-inspector" aria-label="Neuron evidence inspector"><div className="neural-inspector-heading"><Crosshair size={14}/><span>NEURON INSPECTOR</span><span className="neural-inspector-count">{connections.length} LINKS</span>{selectedId && <button aria-label="Clear neuron selection" onClick={() => setSelectedId('')}><X size={12}/></button>}</div>
      {selected && <><div className="neural-node-header"><div className="neural-node-orb" style={{ '--neuron-color': colors[selected.kind] } as React.CSSProperties}><Brain size={selected.kind === 'group' ? 26 : 19}/></div><span className="neural-type" style={{ color: colors[selected.kind] }}>{names[selected.kind].toUpperCase()}</span><h3>{selected.label}</h3><p>{selected.summary}</p><span className="neural-privacy">{selected.kind === 'group' || selected.shared ? 'SHARED KNOWLEDGE' : selected.kind === 'memory' || selected.kind === 'observation' ? 'INDIVIDUAL EVIDENCE' : 'SPACE ENTITY'}</span></div>
        <div className="neural-node-facts">{selected.owner_id && <div><span>Contributor</span><strong>{ownerName(selected.owner_id)}</strong></div>}{selected.status && <div><span>Status</span><strong>{selected.status}</strong></div>}{selected.confidence !== null && <div><span>Confidence</span><strong>{Math.round(selected.confidence * 100)}%</strong></div>}{selected.timestamp && <div><span>Recorded</span><strong>{timestamp(selected.timestamp)}</strong></div>}{selected.evidence.region != null && <div><span>Region</span><strong>Sector {String(selected.evidence.region)}</strong></div>}</div>
        <div className="neural-relationship-heading">CONNECTED KNOWLEDGE <span>{connections.length}</span></div><div className="neural-relationship-list">{connections.slice(0, 30).map(e => { const other = byId.get(e.source === selected.id ? e.target : e.source); return other && <button key={e.id} onClick={() => setSelectedId(other.id)}><i style={{ background: colors[other.kind] }}/><div><small>{e.source === selected.id ? e.relation : `${names[other.kind]} ${e.relation} this`}</small><strong>{other.label}</strong></div><ChevronRight size={13}/></button> })}{!connections.length && <p>No linked evidence yet.</p>}{connections.length > 30 && <small className="neural-more">Showing the first 30 related records.</small>}</div>
        {Object.keys(selected.evidence).length > 0 && <details className="neural-raw"><summary><Fingerprint size={12}/> Inspect stored evidence<ChevronRight size={12}/></summary><pre>{JSON.stringify(selected.evidence, null, 2)}</pre></details>}
        <div className="neural-record-id"><span>RECORD ID</span><code>{selected.source_id}</code></div></>}
      <div className="neural-inspector-foot"><Network size={15}/><span>Evidence connections, not hidden model reasoning.</span></div>
    </aside></div>
    <div className="neural-activity"><div><Activity size={15}/><span>RECENT ACTIVATIONS</span><small>FROM STORED EVENTS</small></div><div className="neural-activation-list">{[...(graph?.recent_events || [])].reverse().slice(0, 4).map(e => <article key={e.id}><time>{timestamp(e.timestamp)}</time><i/><div><strong>{e.type === 'object.merged' ? 'Shared discovery reinforced' : e.type === 'object.discovered' ? 'New discovery connected' : e.type === 'mission.complete' ? 'Mission knowledge consolidated' : e.type === 'group_memory.created' ? 'Memory joined the collective' : e.type.replaceAll('.', ' ').replaceAll('_', ' ')}</strong><p>{String(e.data.summary || e.data.title || e.data.agent_id || e.data.discovered_by || 'Workspace memory updated')}</p></div><ArrowUpRight size={13}/></article>)}{!graph?.recent_events.length && <p className="neural-empty">New observations and shared memories will activate this network.</p>}</div></div>
    <div className="neural-footnote"><Sparkles size={12}/><span>Individual minds. Collective understanding.</span><span>{graph ? `SYNCED ${timestamp(graph.generated_at)}` : 'CONNECTING TO MEMORY'}</span></div>
  </section>
}
