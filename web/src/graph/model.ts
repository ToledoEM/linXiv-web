// Shared vocabulary for the Knowledge Graph page (desktop src/lib/graph/model.ts).

/** Wire types of `GET /api/graph` (desktop src/types/generated.ts, from
 *  linxiv_core::graph); the web server builds the same payload from the CLI. */
export type GraphPaper = {
  /** Node id: SOURCE_FK as a string. */
  id: string
  source_fk: number
  source_id: string
  label: string
  category: string | null
  tags: string[]
  tag_keys: string[]
  has_pdf: boolean
  published: string | null
  url: string | null
  doi: string | null
  summary: string | null
  project_ids: number[]
  author_keys: string[]
}

export type GraphAuthor = {
  /** `author::<AUTHOR_FK>`. */
  id: string
  author_id: number
  label: string
  paper_count: number
}

export type GraphTag = {
  /** `tag::<key>`. */
  id: string
  key: string
  label: string
  paper_count: number
}

export type GraphEdge = { source: string; target: string }

export type GraphProject = {
  id: number
  name: string
  color: string
  tags: string[]
  on_graph: boolean
}

export type GraphView = {
  papers: GraphPaper[]
  authors: GraphAuthor[]
  tags: GraphTag[]
  edges: GraphEdge[]
  categories: string[]
  projects: GraphProject[]
}

export type GraphNodeType = 'paper' | 'author' | 'tag'

/** A node as cytoscape holds it: one id space over all three types. */
export interface GraphNodeData {
  id: string
  type: GraphNodeType
  label: string
  /** Papers only — the vocabulary the project picker speaks. */
  source_id?: string
  /** Authors only — the `/authors/:id` route param. */
  author_id?: number
  /** Authors and tags only — papers on this canvas joined to the node. */
  paper_count?: number
}

/** Lookups the filter and the canvas share, built once per payload — id-space
 *  bookkeeping only; names, canonical tag spelling and degree ride on the payload. */
export interface GraphIndex {
  paperById: Map<string, GraphPaper>
  authorById: Map<string, GraphAuthor>
  tagById: Map<string, GraphTag>
  projectById: Map<number, GraphProject>
  /** Node id -> its type, for edge endpoints and style passes. */
  typeById: Map<string, GraphNodeType>
  /** Paper node id -> the author/tag node ids it is joined to. */
  neighboursByPaper: Map<string, string[]>
  /** Author or tag node id -> the paper node ids joined to it. */
  papersByNode: Map<string, string[]>
}

export function indexView(view: GraphView): GraphIndex {
  const paperById = new Map(view.papers.map((p) => [p.id, p]))
  const authorById = new Map(view.authors.map((a) => [a.id, a]))
  const tagById = new Map(view.tags.map((t) => [t.id, t]))
  const projectById = new Map(view.projects.map((p) => [p.id, p]))

  const typeById = new Map<string, GraphNodeType>()
  for (const p of view.papers) typeById.set(p.id, 'paper')
  for (const a of view.authors) typeById.set(a.id, 'author')
  for (const t of view.tags) typeById.set(t.id, 'tag')

  const neighboursByPaper = new Map<string, string[]>()
  const papersByNode = new Map<string, string[]>()
  for (const e of view.edges) {
    push(neighboursByPaper, e.source, e.target)
    push(papersByNode, e.target, e.source)
  }
  return {
    paperById,
    authorById,
    tagById,
    projectById,
    typeById,
    neighboursByPaper,
    papersByNode,
  }
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const list = map.get(key)
  if (list) list.push(value)
  else map.set(key, [value])
}

/** Trim then lower-case — the rule `linxiv_core::graph::norm_tag` applies
 *  server-side, and the one every PAPER-tag comparison here goes through: a
 *  typed tag is free text, while `GraphPaper.tag_keys` / `GraphTag.key` arrive
 *  normalized. (Project tags fold inline in filter.ts.) */
export function normTag(raw: string): string {
  return raw.trim().toLowerCase()
}
