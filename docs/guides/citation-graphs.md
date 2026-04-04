# Citation Graphs

Scholar MCP provides four tools for exploring citation networks. This guide covers common patterns and strategies.

## Tools overview

| Tool | Use case |
|---|---|
| `get_citations` | "What papers cite this paper?" |
| `get_references` | "What papers does this paper cite?" |
| `get_citation_graph` | "Show me the citation network around these papers" |
| `find_bridge_papers` | "How are these two papers connected?" |

## Basic exploration

### Forward citations

Find papers that cite a known paper:

```
get_citations("DOI:10.48550/arXiv.2005.11401", limit=20)
```

Use filters to narrow results:

```
get_citations(
    "DOI:10.48550/arXiv.2005.11401",
    year_start=2023,
    min_citations=10,
    fields_of_study="Computer Science"
)
```

### Backward references

Find papers cited by a given paper (its bibliography):

```
get_references("DOI:10.48550/arXiv.2005.11401", limit=50)
```

## Graph traversal

`get_citation_graph` performs a BFS (breadth-first search) from seed papers, collecting nodes and edges.

### Single-seed graph

Start from one paper, explore its citation neighborhood:

```
get_citation_graph(
    seed_ids=["CorpusId:218971783"],
    direction="both",
    depth=1,
    max_nodes=50
)
```

### Multi-seed graph

Start from multiple papers to map a research area:

```
get_citation_graph(
    seed_ids=["CorpusId:218971783", "CorpusId:237491837"],
    direction="citations",
    depth=2,
    max_nodes=100
)
```

### Direction strategies

| Direction | Use case |
|---|---|
| `citations` | Find follow-up work and applications |
| `references` | Trace intellectual foundations |
| `both` | Map the full neighborhood around a paper |

### Controlling graph size

!!! tip "Start small"
    Begin with `depth=1` and `max_nodes=50`. Citation graphs grow exponentially with depth -- a popular paper at `depth=2, direction=both` can easily hit 10,000+ nodes.

The `max_nodes` parameter is a hard cap. Once reached, the BFS stops and `stats.truncated` is set to `true`. Filters help focus the graph:

```
get_citation_graph(
    seed_ids=["CorpusId:218971783"],
    direction="both",
    depth=2,
    max_nodes=100,
    year_start=2020,
    min_citations=5
)
```

### Reading the results

The response contains:

```json
{
  "nodes": [{"paperId": "...", "title": "...", ...}],
  "edges": [{"source": "id1", "target": "id2"}],
  "stats": {
    "total_nodes": 42,
    "total_edges": 67,
    "depth_reached": 2,
    "truncated": false
  }
}
```

- **nodes** -- full paper metadata for each paper in the graph
- **edges** -- directed edges from citing paper to cited paper
- **stats.truncated** -- if `true`, the graph was cut short by `max_nodes`

## Bridge papers

`find_bridge_papers` finds the shortest citation path between two papers. This is useful for:

- Discovering how two research areas are connected
- Finding seminal papers that bridge fields
- Understanding intellectual lineage between works

```
find_bridge_papers(
    source_id="CorpusId:218971783",
    target_id="CorpusId:237491837",
    max_depth=4,
    direction="citations"
)
```

The response includes the full path with metadata for each paper:

```json
{
  "found": true,
  "path": [
    {"paperId": "source", "title": "Attention Is All You Need", ...},
    {"paperId": "bridge", "title": "BERT: Pre-training of...", ...},
    {"paperId": "target", "title": "GPT-4 Technical Report", ...}
  ]
}
```

### Tips

- **Direction matters**: `citations` follows forward citations (A cites B); `references` follows backward references. Try both if one direction doesn't find a path.
- **Increase depth carefully**: Each additional depth level can make many API calls. Start with `max_depth=3` or `4`.
- **Caching helps**: Citation and reference lists are cached for 7 days. Repeated bridge searches in the same area are fast.

## Caching behavior

| Data | TTL | Effect |
|---|---|---|
| Paper metadata | 30 days | Nodes reused across graph and bridge queries |
| Citation lists | 7 days | `get_citations` results reused by graph BFS |
| Reference lists | 7 days | `get_references` results reused by graph BFS |
| ID aliases | permanent | DOI-to-S2-ID mappings never expire |

The cache significantly reduces API calls for repeated exploration in the same area. A `get_citation_graph` at `depth=2` that returns 100 nodes might only make 10-20 API calls if the neighborhood was partially explored before.
