export interface Position { x: number; y: number; z: number }
export interface Mind { status: string; objective: string; assignment: string | null; observation_summary: string; decision_summary: string; current_action: string; next_step: string; confidence: number; updated_at: string }
export interface Member { id: string; display_name: string; member_type: 'human' | 'robot'; status: string; capabilities: string[]; telemetry?: { position: Position; battery: number }; active_mind?: Mind; stats?: { memories: number; discoveries: number; regions_visited: number; completed_missions: number } }
export interface Space { id: string; name: string; invite_code: string }
export interface Memory { id: string; title: string; summary: string; category: string; owner_id: string; created_at: string; shared: boolean; mission_id: string | null }
export interface Discovery { id: string; label: string; position: Position; region: string; discovered_by: string; observed_by: string[]; confidence: number; created_at: string; mission_ids: string[] }
export interface Assignment { id: string; agent_id: string; mission_id: string; region: string; status: string; progress: number }
export interface Mission { id: string; command: string; state: string; created_at: string; completed_at: string | null; error: string | null; result: { summary: string; unique_objects: number; regions_cleared: number; participating_agents: number; duplicates_merged: number; coverage: number } | null }
export interface DomainEvent { id?: string; type: string; timestamp: string; data: Record<string, unknown> }
export interface Region { id: string; name: string; xmin: number; xmax: number; ymin: number; ymax: number }
export interface Snapshot { space: Space; members: Member[]; missions: Mission[]; assignments: Assignment[]; events: DomainEvent[]; ai: { provider: string; model: string; mode: string; strict: boolean }; group_mind: { discoveries: Discovery[]; memories: Memory[]; cleared_regions: { region: string; mission_id: string }[] } }
