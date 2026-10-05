import dagre from 'dagre';

/** Nominal card size used by Dagre before measuring the rendered node. */
const NODE_WIDTH = 260;
const NODE_HEIGHT = 96;

const LAYOUT_OPTIONS = {
  rankdir: 'TB',
  nodesep: 80,
  ranksep: 100,
  edgesep: 24,
  marginx: 40,
  marginy: 40,
};

/**
 * Position React Flow nodes with Dagre's hierarchical layout.
 *
 * @param {Array}  nodes  React Flow nodes (ids must match the edge endpoints).
 * @param {Array}  edges  React Flow edges.
 * @param {object} options  `direction`, `nodeWidth`, `nodeHeight` overrides.
 * @returns {Array} A new node array carrying absolute `position` values.
 */
export function layoutGraph(nodes, edges, options = {}) {
  if (!nodes?.length) return [];

  const {
    direction = 'TB',
    nodeWidth = NODE_WIDTH,
    nodeHeight = NODE_HEIGHT,
  } = options;

  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ ...LAYOUT_OPTIONS, rankdir: direction });

  nodes.forEach((node) => {
    graph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges?.forEach((edge) => {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      graph.setEdge(edge.source, edge.target, {}, edge.id);
    }
  });

  dagre.layout(graph);

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id);
    return {
      ...node,
      // Dagre reports the node centre; React Flow expects the top-left corner.
      position: {
        x: Math.round(x - nodeWidth / 2),
        y: Math.round(y - nodeHeight / 2),
      },
    };
  });
}

export default layoutGraph;
