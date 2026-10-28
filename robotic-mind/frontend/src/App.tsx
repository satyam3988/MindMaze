import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowDown, ArrowRight, AudioLines, Bot, Brain, Check, ChevronDown, CircleDot, Copy, Cpu, Eye, Layers, Mic, Network, Plus, ScanLine, Send, Users, Wifi, X } from 'lucide-react'
import { api } from './api'
import type { DomainEvent, Member, Memory, Region, Snapshot, Space } from './types'
import './style.css'
import NeuralMind from './neural/NeuralMind'

const accents = ['#a6e5c4', '#91bdf7', '#c5a5e8', '#e7c28a', '#f391a1']
const stages = ['understanding', 'planning', 'assigning', 'executing', 'synthesizing', 'complete']
const time = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const pos = (value: number) => ((value + 8) / 16) * 640 + 35

function Camera({ agent, large = false }: { agent: Member; large?: boolean }) {
  const [tick, setTick] = useState(0)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => { const id = setInterval(() => setTick(t => t + 1), 700); return () => clearInterval(id) }, [])
  const live = loaded && agent.status !== 'offline'
  return <div className={`camera ${large ? 'large' : ''}`}>
    <div className="camera-placeholder"><ScanLine size={26}/><span>Awaiting camera signal</span></div>
    {agent.status !== 'offline' && <img style={{ opacity: loaded ? 1 : 0 }} alt={`${agent.display_name} camera`} src={`/api/agents/${agent.id}/camera/latest?t=${tick}`} onLoad={() => setLoaded(true)} onError={() => setLoaded(false)} />}
    <div className="camera-top"><span><i className={live ? 'dot' : 'dot muted'}/>{agent.display_name}</span><span>{loaded ? 'RGB · LIVE' : 'NO SIGNAL'}</span></div>
    <div className="crosshair"/><div className="camera-bottom"><span>{agent.active_mind?.assignment ? `SECTOR ${agent.active_mind.assignment}` : 'STANDBY'}</span><span>320 × 240</span></div>
  </div>
}

function World({ data, regions, onSelect, selected }: { data: Snapshot; regions: Region[]; onSelect: (id: string) => void; selected: string }) {
  const mission = data.missions.at(-1)
  const robots = data.members.filter(m => m.member_type === 'robot')
  const cleared = data.group_mind.cleared_regions.filter(r => r.mission_id === mission?.id).map(r => r.region)
  return <div className="world"><div className="map-label"><span><i className="dot"/> LIVE TELEMETRY</span><span>WAREHOUSE ALPHA / TOP VIEW</span></div>
    <svg viewBox="0 0 710 710" role="img" aria-label="Live warehouse map with sectors, robot positions and discoveries">
      <defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="#26342e" strokeWidth=".7"/></pattern></defs>
      <rect x="35" y="35" width="640" height="640" fill="url(#grid)" stroke="#52665b" strokeWidth="2"/>
      {regions.map(r => <g key={r.id}><rect x={pos(r.xmin)} y={pos(-r.ymax)} width={(r.xmax-r.xmin)*40} height={(r.ymax-r.ymin)*40} fill={cleared.includes(r.id) ? '#84d6ac14' : 'transparent'} stroke="#435147" strokeDasharray="5 7"/><text x={pos(r.xmin)+18} y={pos(-r.ymax)+32} fill={cleared.includes(r.id) ? '#a6e5c4' : '#7c8b83'} fontSize="14" fontFamily="monospace">{r.name.toUpperCase()}{cleared.includes(r.id) ? ' / CLEAR' : ''}</text></g>)}
      {[[-4,0],[4,0],[0,4],[0,-4]].map(([x,y]) => <g key={`${x},${y}`}><rect x={pos(x)-25} y={pos(-y)-13} width="50" height="26" fill="#303e35" stroke="#59675f"/><path d={`M${pos(x)-17},${pos(-y)-9}v18m9,-18v18m9,-18v18m9,-18v18`} stroke="#657267" strokeWidth="2"/></g>)}
      {data.group_mind.discoveries.map((d,i) => <g key={d.id}><circle cx={pos(d.position.x)} cy={pos(-d.position.y)} r="15" fill="#f17c6d15" stroke="#ec8b78" strokeDasharray="3 4"/><rect x={pos(d.position.x)-5} y={pos(-d.position.y)-5} width="10" height="10" fill="#ef8b78"/><text x={pos(d.position.x)+20} y={pos(-d.position.y)+4} fill="#f1aa9a" fontSize="11" fontFamily="monospace">OBJ {String(i+1).padStart(2,'0')}</text></g>)}
      {robots.map((robot,i) => { const p = robot.telemetry?.position; if (!p) return null; const x=pos(p.x), y=pos(-p.y), color=accents[i%accents.length]; return <g key={robot.id} onClick={() => onSelect(robot.id)} className="map-robot" tabIndex={0} role="button" aria-label={`Inspect ${robot.display_name}`} onKeyDown={e => e.key === 'Enter' && onSelect(robot.id)}><circle cx={x} cy={y} r={selected === robot.id ? 26 : 18} fill={`${color}12`} stroke={color} strokeWidth={selected === robot.id ? 1.5 : .5}/><path d={`M${x-9},${y-9}l18,18m-18,0l18,-18`} stroke={color} strokeWidth="3"/>{[[-9,-9],[9,9],[-9,9],[9,-9]].map(([a,b]) => <circle key={`${a},${b}`} cx={x+a} cy={y+b} r="4" fill="#17231b" stroke={color}/>)}<text x={x+30} y={y+4} fill={color} fontSize="12" fontFamily="monospace">{robot.display_name}</text></g> })}
      {robots.length === 0 && <text x="355" y="355" textAnchor="middle" fill="#7d9183" fontSize="14">Launch Webots to connect your robots</text>}
      <text x="36" y="700" fill="#6c7e72" fontSize="10" fontFamily="monospace">−8m</text><text x="644" y="700" fill="#6c7e72" fontSize="10" fontFamily="monospace">+8m</text>
    </svg><div className="map-legend"><span><i className="legend-square"/> Robot</span><span><i className="legend-square coral"/> Discovery</span><span><i className="legend-square cleared"/> Cleared area</span><span className="ml-auto">16 × 16 METERS</span></div></div>
}

interface SpeechResult { results: { transcript: string }[][] }
interface Speech { lang: string; interimResults: boolean; onresult: ((event: SpeechResult) => void) | null; onend: (() => void) | null; onerror: (() => void) | null; start(): void; stop(): void }
type SpeechConstructor = new () => Speech
const speechWindow = window as unknown as { SpeechRecognition?: SpeechConstructor; webkitSpeechRecognition?: SpeechConstructor }

export default function App() {
  const [spaceId, setSpaceId] = useState(localStorage.getItem('rm-space') || '')
  const [spaces, setSpaces] = useState<Space[]>([])
  const [data, setData] = useState<Snapshot | null>(null)
  const [regions, setRegions] = useState<Region[]>([])
  const [connected, setConnected] = useState(false)
  const [selected, setSelected] = useState('')
  const [view, setView] = useState(new URLSearchParams(location.search).get('view') === 'group' ? 'group' : 'control')
  const [tab, setTab] = useState('active')
  const [memories, setMemories] = useState<Memory[]>([])
  const [command, setCommand] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [dialog, setDialog] = useState('')
  const [name, setName] = useState(localStorage.getItem('rm-name') || 'Satyam')
  const [spaceName, setSpaceName] = useState('Warehouse Alpha')
  const [invite, setInvite] = useState('')
  const [listening, setListening] = useState(false)
  const [copied, setCopied] = useState(false)
  const recognition = useRef<Speech | null>(null)
  const [refreshTick, setRefreshTick] = useState(0)
  const loadSpaces = useCallback(async () => {
    const list = await api<Space[]>('/spaces'); setSpaces(list)
    if (!spaceId && list.length) setSpaceId(list[0].id)
  }, [spaceId])
  useEffect(() => { loadSpaces().catch(e => setError(e.message)); api<{ regions: Region[] }>('/world').then(w => setRegions(w.regions)).catch(e => setError(e.message)) }, [loadSpaces])
  useEffect(() => {
    if (!spaceId) return
    localStorage.setItem('rm-space', spaceId)
    let closed = false, socket: WebSocket | null = null
    let reconnect: ReturnType<typeof setTimeout>
    let refresh: ReturnType<typeof setTimeout> | undefined
    const fetchState = () => { api<Snapshot>(`/spaces/${spaceId}`).then(d => { if (!closed) setData(d) }).catch(e => !closed && setError(e.message)) }
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/spaces/${spaceId}`)
      socket.onopen = () => { setConnected(true); setError('') }
      socket.onmessage = e => {
        const event = JSON.parse(e.data) as DomainEvent & { data: Snapshot }
        if (event.type === 'snapshot') { setData(event.data); return }
        if (['ping','robot.heartbeat','camera.updated'].includes(event.type)) return
        if (!refresh) refresh = setTimeout(() => { fetchState(); setRefreshTick(t => t+1); refresh = undefined }, 300)
      }
      socket.onclose = () => { setConnected(false); if (!closed) reconnect = setTimeout(connect, 1500) }
      socket.onerror = () => socket?.close()
    }
    setData(null); fetchState(); connect()
    const fallback = setInterval(fetchState, 5000)
    return () => { closed = true; clearTimeout(reconnect); clearTimeout(refresh); clearInterval(fallback); socket?.close() }
  }, [spaceId])
  useEffect(() => { if (!selected) { setMemories([]); return }; api<Memory[]>(`/agents/${selected}/memories`).then(setMemories).catch(e => setError(e.message)) }, [selected, refreshTick])
  const robots = data?.members.filter(m => m.member_type === 'robot') || []
  const agent = robots.find(m => m.id === selected) || robots[0]
  const mission = data?.missions.at(-1)
  const assignments = data?.assignments.filter(a => a.mission_id === mission?.id) || []
  const cleared = assignments.filter(a => a.status === 'completed').length
  const coverage = assignments.length ? Math.round(cleared / assignments.length * 100) : 0
  const busy = Boolean(mission && !['complete','failed'].includes(mission.state))
  const SpeechAPI = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition

  async function submit() {
    if (!command.trim()) return
    setSubmitting(true); setError('')
    try { await api(`/spaces/${spaceId}/commands`, { text: command }); setCommand('') } catch (e) { setError((e as Error).message) } finally { setSubmitting(false) }
  }
  async function saveSpace(e: React.FormEvent) {
    e.preventDefault(); setError('')
    try {
      const result = await api<{ space: Space; member: { id: string } }>(dialog === 'join' ? '/spaces/join' : '/spaces', dialog === 'join' ? { invite_code: invite.toUpperCase(), display_name: name } : { name: spaceName, display_name: name })
      localStorage.setItem('rm-name', name); localStorage.setItem('rm-member', result.member.id)
      setSpaceId(result.space.id); setDialog(''); await loadSpaces()
    } catch (e) { setError((e as Error).message) }
  }
  function voice() {
    if (!SpeechAPI) return
    if (listening) { recognition.current?.stop(); return }
    const r = new SpeechAPI(); recognition.current = r; r.lang = 'en-US'; r.interimResults = false
    r.onresult = event => setCommand(event.results[0][0].transcript)
    r.onend = () => setListening(false); r.onerror = () => { setListening(false); setError('Voice input unavailable. You can type your mission below.') }
    r.start(); setListening(true)
  }
  const selectAgent = (id: string) => { setSelected(id); setTab('active') }
  const copy = async () => { if (data) { await navigator.clipboard.writeText(data.space.invite_code); setCopied(true); setTimeout(() => setCopied(false), 1800) } }

  return <div className="app">
    <header><a className="brand" href="/"><div className="brand-symbol"><Network size={23}/></div><span>ROBOTIC<span className="light">MIND</span><small>SHARED INTELLIGENCE, IN MOTION.</small></span></a>
      <div className="space-switch"><Layers size={16}/><select aria-label="Select space" value={spaceId} onChange={e => setSpaceId(e.target.value)}>{!spaces.length && <option value="">Select a space</option>}{spaces.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select><ChevronDown size={13}/></div>
      <div className="header-right"><span className="connection"><i className={connected ? 'dot' : 'dot muted'}/>{connected ? 'SYSTEM LIVE' : 'CONNECTING'}</span><button className="invite-btn" onClick={() => setDialog('join')}><Users size={14}/> Join space</button><button className="avatar" onClick={() => setDialog('create')} title="Create space">{name.slice(0,1).toUpperCase()}</button></div>
    </header>
    {error && <div className="error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={15}/></button></div>}
    <div className={`layout ${view==='group' ? 'neural-layout' : ''}`}><aside className="sidebar"><div className="workspace-label">WORKSPACE <button onClick={() => setDialog('create')} aria-label="Create space"><Plus size={15}/></button></div>
      <button className={`nav ${view==='control' ? 'selected' : ''}`} onClick={() => setView('control')}><Activity size={17}/> Mission control <span className="nav-dot"/></button>
      <button className={`nav ${view==='group' ? 'selected' : ''}`} onClick={() => setView('group')}><Brain size={17}/> Group Mind <span className="nav-count">{data?.group_mind.discoveries.length || 0}</span></button>
      <button className={`nav ${view==='history' ? 'selected' : ''}`} onClick={() => setView('history')}><Layers size={17}/> Mission history</button>
      <div className="member-heading">SPACE MEMBERS <span>{data?.members.length || 0}</span></div>
      {data?.members.filter(m => m.member_type === 'human').map(m => <div className="human" key={m.id}><div className="human-avatar">{m.display_name.slice(0,1)}</div><div><strong>{m.display_name}</strong><small>Human · Space member</small></div></div>)}
      {robots.map((r,i) => <button className={`member ${agent?.id === r.id ? 'active' : ''}`} key={r.id} onClick={() => selectAgent(r.id)}><div className="robot-icon" style={{ color: accents[i%accents.length] }}><Bot size={21}/><i className={r.status==='online' ? 'dot' : 'dot muted'}/></div><div><strong>{r.display_name}</strong><small>{r.active_mind?.status === 'searching' ? `Searching · Sector ${r.active_mind.assignment}` : r.status === 'online' ? 'Ready for a mission' : r.status}</small></div><span className="member-memories">{r.stats?.memories || 0}<Brain size={10}/></span></button>)}
      {!robots.length && <p className="sidebar-empty">Your robots will appear here when they join with this space’s invite code.</p>}
      <button className="add-member" onClick={copy}><Plus size={15}/> Invite a member</button>
      <div className="sidebar-bottom"><div className="network-visual"><Network size={38}/></div><strong>One space. Many minds.</strong><p>Every discovery makes the whole team smarter.</p><button className="invite-code" onClick={copy}>{data?.space.invite_code || 'CREATE A SPACE'}{copied ? <Check size={13}/> : <Copy size={13}/>}</button><div className="version"><span>ROBOTIC MIND</span><span>v0.1 / LOCAL</span></div></div>
    </aside>
    <main><div className="page-heading"><div><div className="eyebrow">WORKSPACE / {data?.space.name.toUpperCase() || 'GET STARTED'}</div><h1>{view==='group' ? 'Group Mind' : view==='history' ? 'Mission history' : 'Mission control'}<span className="heading-dot"/></h1><p>{view==='group' ? 'The living network behind your team?s shared understanding.' : 'A shared cognitive workspace for humans and autonomous machines.'}</p></div><span className="local-badge"><Wifi size={13}/> LOCAL NETWORK</span></div>
      {!data && <section className="welcome"><Brain size={40}/><h2>{spaceId ? 'Connecting to your workspace' : 'Build a space for shared intelligence.'}</h2><p>Connect people and robots. Give them a mission. Watch knowledge grow.</p><button className="primary" onClick={() => setDialog('create')}>Create a space <ArrowRight size={16}/></button></section>}
      {data && <><div className="metrics"><div><span>AGENTS ONLINE</span><strong>{robots.filter(r => r.status==='online').length}<small>/ {robots.length}</small></strong><i className="dot"/></div><div><span>SEARCH COVERAGE</span><strong>{coverage}<small>%</small></strong><div className="mini-progress"><i style={{ width: `${coverage}%` }}/></div></div><div><span>SHARED DISCOVERIES</span><strong>{data.group_mind.discoveries.length.toString().padStart(2,'0')}</strong><Eye size={19}/></div><div><span>COLLECTIVE MEMORIES</span><strong>{data.group_mind.memories.length.toString().padStart(2,'0')}</strong><Brain size={19}/></div></div>
      {view==='control' && <><section className="mission-panel"><div className="section-heading"><span><CircleDot size={15}/> CURRENT MISSION</span><span className={`status-chip ${mission?.state==='failed' ? 'failed' : ''}`}>{mission?.state.toUpperCase() || 'STANDBY'}</span></div><h2>{mission?.command || 'Your team is ready for its next mission.'}</h2><div className="mission-meta"><span><Cpu size={13}/>{data.ai.mode === 'mock' ? 'AI: DEVELOPMENT MOCK' : 'AI: NVIDIA NEMOTRON'}</span><span>{data.ai.provider}</span>{mission && <span>{cleared}/{assignments.length} sectors cleared</span>}</div>
      {mission && <div className="stages">{stages.map((s,i) => <span className={stages.indexOf(mission.state) >= i ? 'done' : ''} key={s}><i>{stages.indexOf(mission.state)>i ? <Check size={9}/> : i+1}</i>{s === 'assigning' ? 'Assigning agents' : s}{i<stages.length-1 && <div/>}</span>)}</div>}
      {mission?.error && <p className="mission-error">{mission.error}</p>}
      {mission?.result && <div className="result"><Check size={18}/><div><strong>Mission complete · {mission.result.unique_objects} unique red objects found</strong><p>{mission.result.summary}</p><small>{mission.result.regions_cleared} sectors · {mission.result.participating_agents} robots · {mission.result.duplicates_merged} duplicates merged · 100% coverage</small></div></div>}
      </section><section className="world-panel"><div className="section-heading"><span><ScanLine size={15}/> WORLD VIEW</span><span className="tiny">ENU COORDINATES · METERS</span></div><World data={data} regions={regions} selected={agent?.id || ''} onSelect={selectAgent}/></section>
      <section className="feeds"><div className="section-heading"><span><Eye size={15}/> ROBOT VISION <b>{robots.length} FEEDS</b></span><span className="tiny">RGB CAMERAS / ~1.4 FPS</span></div><div className="camera-grid">{robots.map(r => <button key={r.id} onClick={() => { selectAgent(r.id); setTab('camera') }}><Camera agent={r}/></button>)}{!robots.length && <div className="feed-empty">No robot cameras connected. Launch the Webots warehouse to begin.</div>}</div></section></>}
      {view==='group' && <><NeuralMind spaceId={spaceId} data={data} connected={connected}/><details className="neural-ledger"><summary>Explore the shared knowledge records</summary><section className="group-view"><div className="section-heading"><span><Network size={16}/> PERSISTENT SHARED KNOWLEDGE</span><span className="tiny">PROVENANCE INCLUDED</span></div><div className="discovery-grid">{data.group_mind.discoveries.map((d,i) => <article className="discovery" key={d.id}><span className="discovery-id"><i/> OBJECT {String(i+1).padStart(2,'0')}</span><h2>Red object</h2><p>Sector {d.region} · ({d.position.x.toFixed(2)}, {d.position.y.toFixed(2)}, {d.position.z.toFixed(1)})</p><div className="fact"><span>Discovered by</span><strong>{d.discovered_by}</strong></div><div className="fact"><span>Observed by</span><strong>{d.observed_by.join(', ')}</strong></div><div className="fact"><span>Confidence</span><strong>{Math.round(d.confidence*100)}%</strong></div><small>Shared {time(d.created_at)}</small></article>)}</div>{!data.group_mind.discoveries.length && <div className="empty-state"><Network size={30}/><h3>Shared knowledge starts with a discovery.</h3><p>Confirmed camera observations will appear here with their contributors.</p></div>}<h3 className="subheading">Shared memories</h3><MemoryList memories={data.group_mind.memories}/></section></details></>}
      {view==='history' && <section className="history-view">{[...data.missions].reverse().map(m => <article key={m.id}><span className="eyebrow">{new Date(m.created_at).toLocaleString()} · {m.state.toUpperCase()}</span><h2>{m.command}</h2><p>{m.result?.summary || m.error || 'Mission in progress'}</p></article>)}{!data.missions.length && <div className="empty-state">No missions yet. Start one from the command bar.</div>}</section>}
      <section className="timeline-panel"><div className="section-heading"><span><Activity size={15}/> LIVE ACTIVITY</span><span className="tiny">{data.events.length} RECENT EVENTS</span></div><div className="timeline">{[...data.events].reverse().slice(0,8).map((e,i) => <div className="timeline-event" key={e.id || i}><time>{time(e.timestamp)}</time><i className={e.type.includes('discovered') ? 'event-dot discovery-dot' : 'event-dot'}/><span>{eventLabel(e)}</span><small>{e.type.split('.')[0]}</small></div>)}{!data.events.length && <p className="empty-text">Waiting for activity.</p>}</div></section></>}
      <footer><span>HUMANS + ROBOTS + SHARED MEMORY</span><span><i className={connected ? 'dot' : 'dot muted'}/> {connected ? 'LIVE SPACE CONNECTION' : 'SPACE DISCONNECTED'}</span></footer>
    </main>
    {view!=='group' && <aside className="inspector"><div className="inspector-top"><Brain size={16}/><span>AGENT INSPECTOR</span><div className="tiny">LIVE STATE</div></div>{agent ? <><div className="agent-title"><div className="agent-portrait"><Bot size={35}/></div><h2>{agent.display_name}</h2><span className="online"><i className={agent.status==='online' ? 'dot' : 'dot muted'}/>{agent.status.toUpperCase()}</span><p>Autonomous space member</p></div><div className="capabilities">{agent.capabilities.map(c => <span key={c}>{c.replace('_',' ')}</span>)}</div><div className="inspector-tabs">{['active','deep','camera','history'].map(t => <button className={tab===t ? 'active' : ''} key={t} onClick={() => { setTab(t); if (!selected) setSelected(agent.id) }}>{t==='active' ? 'Active Mind' : t==='deep' ? 'Deep Mind' : t.charAt(0).toUpperCase()+t.slice(1)}</button>)}</div>
      {tab==='active' && <div className="mind-state"><div className="mind-disclaimer"><CircleDot size={12}/> Structured application state</div>{[['Objective',agent.active_mind?.objective],['Seeing',agent.active_mind?.observation_summary],['Decision summary',agent.active_mind?.decision_summary],['Current action',agent.active_mind?.current_action],['Next step',agent.active_mind?.next_step]].map(([label,value],i) => <div className="mind-row" key={label}><span className="mind-number">0{i+1}</span><div><label>{label}</label><p>{value || 'Awaiting robot update'}</p></div></div>)}<div className="confidence"><span>CONFIDENCE</span><strong>{Math.round((agent.active_mind?.confidence || 0)*100)}%</strong><div><i style={{ width: `${(agent.active_mind?.confidence || 0)*100}%` }}/></div></div><div className="position-readout"><span>POSITION</span>{['x','y','z'].map(k => <div key={k}><small>{k.toUpperCase()}</small>{agent.telemetry?.position[k as 'x'|'y'|'z'].toFixed(2) || '—'}<small>m</small></div>)}</div></div>}
      {tab==='deep' && <div className="inspector-content"><div className="memory-stats"><div><strong>{agent.stats?.memories || 0}</strong><span>Memories</span></div><div><strong>{agent.stats?.regions_visited || 0}</strong><span>Regions visited</span></div></div><MemoryList memories={memories}/></div>}
      {tab==='camera' && <div className="inspector-content"><Camera agent={agent} large/><p className="empty-text">This robot’s own downward RGB camera. Detections come from color segmentation.</p></div>}
      {tab==='history' && <div className="inspector-content"><MemoryList memories={memories.filter(m => ['task_outcome','mission','summary'].includes(m.category))}/></div>}
      <div className="inspector-bottom"><Network size={18}/><div><strong>Connected to Group Mind</strong><p>{data?.group_mind.discoveries.length || 0} discoveries available to this agent</p></div><ArrowDown size={13}/></div></> : <div className="empty-state"><Bot size={35}/><h3>A mind for every machine.</h3><p>Select a connected robot to inspect its current state, memory, and camera.</p></div>}</aside>}</div>
    <div className={`command-wrap ${view==='group' ? 'neural-command' : ''}`}><div className="command-icon"><AudioLines size={22}/></div><div className="command-input"><label htmlFor="mission-command">GIVE YOUR TEAM A MISSION</label><input id="mission-command" value={command} onChange={e => setCommand(e.target.value)} onKeyDown={e => e.key==='Enter' && !busy && submit()} placeholder="Find all red objects. Split up and avoid searching the same places twice." disabled={!data}/></div><button className={`mic ${listening ? 'listening' : ''}`} aria-label="Dictate mission" title={SpeechAPI ? 'Dictate mission' : 'Speech recognition unavailable in this browser'} disabled={!SpeechAPI || !data} onClick={voice}><Mic size={19}/></button><button className="primary submit" onClick={submit} disabled={!command.trim() || !data || busy || submitting}><span>{busy ? 'Mission running' : submitting ? 'Submitting' : 'Launch mission'}</span><Send size={15}/></button></div>
    {dialog && <div className="modal-backdrop"><form className="modal" onSubmit={saveSpace}><button type="button" className="modal-close" aria-label="Close" onClick={() => setDialog('')}><X size={18}/></button><Network size={28}/><h2>{dialog==='join' ? 'Join a shared space' : 'Create a shared space'}</h2><p>A place for people and machines to learn together.</p><label>Your name<input required maxLength={80} value={name} onChange={e => setName(e.target.value)}/></label>{dialog==='join' ? <label>Invite code<input required pattern="RM-[A-Z2-9]{6}" placeholder="RM-XXXXXX" value={invite} onChange={e => setInvite(e.target.value.toUpperCase())}/></label> : <label>Space name<input required maxLength={80} value={spaceName} onChange={e => setSpaceName(e.target.value)}/></label>}{error && <p className="mission-error">{error}</p>}<button className="primary" type="submit">{dialog==='join' ? 'Join space' : 'Create space'}<ArrowRight size={15}/></button><button type="button" className="text-button" onClick={() => setDialog(dialog==='join' ? 'create' : 'join')}>{dialog==='join' ? 'Create a new space instead' : 'Have an invite? Join a space'}</button></form></div>}
  </div>
}

function eventLabel(event: DomainEvent) {
  const d = event.data
  if (typeof d.summary === 'string') return d.summary
  if (event.type === 'llm.completed') return `${d.provider} completed ${d.purpose}`
  if (event.type.startsWith('assignment.')) return `${d.agent_id} → Sector ${d.region} · ${event.type.split('.')[1]}`
  if (event.type === 'robot.connected') return `${d.display_name} joined the space`
  if (event.type === 'object.discovered') return `${d.discovered_by} discovered a red object in Sector ${d.region}`
  if (event.type === 'object.merged') return 'Duplicate observation merged into shared discovery'
  if (event.type === 'active_mind.updated') return `${d.agent_id} · ${d.current_action}`
  return event.type.replaceAll('.', ' ').replaceAll('_', ' ')
}
function MemoryList({ memories }: { memories: Memory[] }) { return <div className="memory-list">{[...memories].reverse().slice(0,40).map(m => <article key={m.id}><div><time>{time(m.created_at)}</time><span>{m.category}</span></div><strong>{m.title}</strong><p>{m.summary}</p>{m.shared && <small><Network size={11}/> Shared by {m.owner_id}</small>}</article>)}{!memories.length && <p className="empty-text">Memories will grow as this team explores.</p>}</div> }
