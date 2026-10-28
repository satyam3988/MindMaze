export type NodeKind = 'group' | 'human' | 'robot' | 'mission' | 'assignment' | 'region' | 'observation' | 'memory' | 'discovery'
export interface MindNode {
  id: string; kind: NodeKind; label: string; summary: string; source_id: string
  owner_id: string | null; timestamp: string | null; confidence: number | null
  shared: boolean; status: string | null; evidence: Record<string, unknown>
}
export interface MindEdge { id: string; source: string; target: string; relation: string }
export interface MindGraph {
  space_id: string; generated_at: string; nodes: MindNode[]; edges: MindEdge[]
  counts: Partial<Record<NodeKind, number>>; total_nodes: number; truncated: boolean
  recent_events: { id: string; type: string; timestamp: string; data: Record<string, unknown> }[]
}
export interface PlacedNode extends MindNode { x: number; y: number; radius: number }
export const colors: Record<NodeKind, string> = {
  group: '#e5e6ff', human: '#f2d1a5', robot: '#69dcfa', mission: '#b39bff',
  assignment: '#8b9eea', region: '#7ebfac', observation: '#7499c9',
  memory: '#a68bed', discovery: '#ffb87c',
}
export const names: Record<NodeKind, string> = {
  group: 'Collective', human: 'Human', robot: 'Robot', mission: 'Mission',
  assignment: 'Assignment', region: 'Region', observation: 'Observation',
  memory: 'Memory', discovery: 'Discovery',
}
export function hash(value: string): number {
  let result = 2166136261
  for (let i = 0; i < value.length; i++) result = Math.imul(result ^ value.charCodeAt(i), 16777619)
  return result >>> 0
}
export function placeNodes(nodes: MindNode[]): PlacedNode[] {
  const buckets = new Map<string, MindNode[]>()
  for (const node of nodes) {
    const key = node.kind === 'memory' ? (node.shared ? 'shared' : 'private') : node.kind
    const bucket = buckets.get(key) || []; bucket.push(node); buckets.set(key, bucket)
  }
  const anchors: Record<string, [number, number, number, number]> = {
    group: [500, 326, 0, 0], robot: [270, 361, 100, 70], human: [421, 502, 25, 28],
    region: [357, 178, 85, 65], mission: [717, 300, 95, 105],
    discovery: [655, 177, 83, 60], observation: [260, 250, 92, 90],
    assignment: [376, 356, 65, 130], shared: [682, 443, 135, 90],
    private: [282, 454, 92, 72],
  }
  const sizes: Record<NodeKind, number> = { group: 23, robot: 12, human: 10, mission: 8, discovery: 9, region: 7, observation: 3, assignment: 4, memory: 4 }
  const result: PlacedNode[] = []
  for (const [key, bucket] of buckets) {
    bucket.sort((a, b) => a.id.localeCompare(b.id))
    const [cx, cy, rx, ry] = anchors[key]
    bucket.forEach((node, index) => {
      const angle = index * 2.39996323 + .7 + (hash(node.id) % 100) / 350
      const radius = Math.sqrt((index + .5) / bucket.length)
      result.push({ ...node, x: cx + Math.cos(angle) * rx * radius, y: cy + Math.sin(angle) * ry * radius, radius: sizes[node.kind] })
    })
  }
  // Keep all evidence neurons distinct without inventing additional graph nodes.
  for (let step = 0; step < 32; step++) {
    for (let i = 0; i < result.length; i++) for (let j = i + 1; j < result.length; j++) {
      const a = result[i], b = result[j]
      const dx = b.x - a.x || .1, dy = b.y - a.y || .1
      const distance = Math.hypot(dx, dy), minimum = a.radius + b.radius + 10
      if (distance < minimum) {
        const push = (minimum - distance) * .28
        if (a.kind !== 'group') { a.x -= dx / distance * push; a.y -= dy / distance * push }
        if (b.kind !== 'group') { b.x += dx / distance * push; b.y += dy / distance * push }
      }
    }
  }
  return result
}
export function connectionPath(a: PlacedNode, b: PlacedNode, id: string) {
  const bend = ((hash(id) % 80) - 40) * .55
  return `M ${a.x} ${a.y} Q ${(a.x + b.x) / 2 + bend} ${(a.y + b.y) / 2 - bend} ${b.x} ${b.y}`
}
