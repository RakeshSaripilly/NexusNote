import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import { AlertTriangle, Loader2, Network } from 'lucide-react';

import CustomConceptNode from './components/CustomConceptNode';
import ProvenanceDrawer from './components/ProvenanceDrawer';
import ArtifactLightbox from './components/ArtifactLightbox';
import TopBar from './components/TopBar';
import { describeError, fetchConcept, fetchGraph, uploadDocument } from './api/client';
import { layoutGraph } from './utils/layout';

const NODE_TYPES = { customConceptNode: CustomConceptNode };

const DEFAULT_EDGE_OPTIONS = {
  type: 'smoothstep',
  style: { stroke: '#475569', strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: '#475569' },
};

/** Translate the API graph payload into React Flow nodes/edges. */
function toFlowElements(graph) {
  const nodes = (graph.nodes ?? []).map((node) => ({
    id: node.id,
    type: node.type ?? 'customConceptNode',
    data: {
      label: node.data?.label ?? 'Untitled',
      factCount: node.data?.factCount ?? 0,
      artifactCount: node.data?.artifactCount ?? 0,
    },
  }));

  const known = new Set(nodes.map((node) => node.id));
  const edges = (graph.edges ?? [])
    .filter((edge) => known.has(edge.source) && known.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: (edge.label ?? 'relates_to').replace(/_/g, ' '),
      animated: edge.animated ?? true,
    }));

  return { nodes, edges };
}

function GraphCanvas() {
  const { fitView } = useReactFlow();
  // `Background`, `Controls` and `MiniMap` are declarative children of <ReactFlow>,
  // so the canvas overlays live here purely to read the React Flow instance.
  return (
    <>
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1e293b" />
      <Controls className="!rounded-lg !border-slate-700 !bg-slate-900 !text-slate-300" />
      <MiniMap
        pannable
        zoomable
        nodeColor="#0e7490"
        maskColor="rgba(2, 6, 23, 0.75)"
        className="!rounded-lg !border !border-slate-700 !bg-slate-900"
      />
      <button
        type="button"
        onClick={() => fitView({ padding: 0.2, duration: 400 })}
        className="absolute bottom-6 right-6 z-10 rounded-lg border border-slate-700 bg-slate-900/90 px-3 py-2 text-xs text-slate-300 backdrop-blur transition-colors hover:border-slate-500 hover:text-white"
      >
        Fit view
      </button>
    </>
  );
}

function Workspace() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphError, setGraphError] = useState('');
  const [status, setStatus] = useState('');

  const [selectedId, setSelectedId] = useState(null);
  const [concept, setConcept] = useState(null);
  const [conceptLoading, setConceptLoading] = useState(false);
  const [conceptError, setConceptError] = useState('');

  const [lightboxIndex, setLightboxIndex] = useState(null);

  const loadGraph = useCallback(async () => {
    setGraphLoading(true);
    setGraphError('');
    try {
      const graph = await fetchGraph();
      const { nodes: rawNodes, edges: rawEdges } = toFlowElements(graph);
      setNodes(layoutGraph(rawNodes, rawEdges));
      setEdges(rawEdges);
    } catch (error) {
      setGraphError(describeError(error, 'Could not load the knowledge graph.'));
    } finally {
      setGraphLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Fetch deep lineage whenever a different node is selected.
  useEffect(() => {
    if (!selectedId) {
      setConcept(null);
      setConceptError('');
      return undefined;
    }

    let cancelled = false;
    setConceptLoading(true);
    setConceptError('');

    fetchConcept(selectedId)
      .then((data) => {
        if (!cancelled) setConcept(data);
      })
      .catch((error) => {
        if (!cancelled) {
          setConcept(null);
          setConceptError(describeError(error, 'Could not load provenance.'));
        }
      })
      .finally(() => {
        if (!cancelled) setConceptLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const handleUpload = useCallback(
    async (file, setProgress) => {
      const summary = await uploadDocument(file, (event) => {
        if (!event.total) return;
        setProgress(Math.round((event.loaded / event.total) * 100));
      });

      setStatus(
        `Ingested ${summary.file_name}: ${summary.chunks_processed} chunks, ` +
          `${summary.artifacts_extracted} artifacts, ` +
          `${summary.concepts_touched.length} concepts touched.`,
      );
      await loadGraph();
      return summary;
    },
    [loadGraph],
  );

  const handleRelayout = useCallback(() => {
    setNodes((current) => layoutGraph(current, edges));
  }, [edges]);

  const nodeCount = nodes.length;
  const edgeCount = edges.length;
  const lightboxArtifacts = concept?.artifacts ?? [];

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-200">
      <TopBar
        nodes={nodes}
        onUpload={handleUpload}
        onRelayout={handleRelayout}
      />

      {status && (
        <div className="flex items-center justify-between gap-4 border-b border-slate-800 bg-slate-900/60 px-5 py-2 text-xs text-slate-400">
          <span className="truncate">{status}</span>
          <button type="button" onClick={() => setStatus('')} className="shrink-0 text-slate-500 hover:text-slate-200">
            Dismiss
          </button>
        </div>
      )}

      <main className="relative flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={NODE_TYPES}
          defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onPaneClick={() => setSelectedId(null)}
          nodesDraggable
          nodesConnectable={false}
          minZoom={0.15}
          maxZoom={2.5}
          proOptions={{ hideAttribution: true }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
        >
          <GraphCanvas />
        </ReactFlow>

        {graphLoading && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-slate-950/50 backdrop-blur-sm">
            <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-300">
              <Loader2 size={16} className="animate-spin" />
              Loading knowledge graph…
            </div>
          </div>
        )}

        {!graphLoading && graphError && (
          <div className="absolute left-1/2 top-6 z-10 w-full max-w-lg -translate-x-1/2 px-4">
            <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-400" />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-red-200">{graphError}</p>
                <button
                  type="button"
                  onClick={loadGraph}
                  className="mt-2 rounded-md border border-red-400/40 px-2.5 py-1 text-xs text-red-200 transition-colors hover:bg-red-500/20"
                >
                  Retry
                </button>
              </div>
            </div>
          </div>
        )}

        {!graphLoading && !graphError && nodeCount === 0 && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
            <div className="max-w-sm rounded-2xl border border-slate-800 bg-slate-900/80 px-6 py-8 text-center backdrop-blur">
              <Network size={28} className="mx-auto text-slate-600" />
              <h3 className="mt-4 text-sm font-semibold text-slate-200">
                The graph is empty
              </h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
                Upload a PDF, text file or image and NexusNote will chunk it, extract
                diagrams and merge the knowledge into concepts.
              </p>
            </div>
          </div>
        )}

        {!graphLoading && !graphError && nodeCount > 0 && (
          <div className="pointer-events-none absolute bottom-6 left-6 z-10 rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2 text-[11px] text-slate-400 backdrop-blur">
            <span className="font-medium text-slate-200">{nodeCount}</span> concepts
            {' · '}
            <span className="font-medium text-slate-200">{edgeCount}</span> relations
          </div>
        )}

        <ProvenanceDrawer
          open={Boolean(selectedId)}
          concept={concept}
          loading={conceptLoading}
          error={conceptError}
          onClose={() => setSelectedId(null)}
          onOpenArtifact={setLightboxIndex}
        />
      </main>

      {lightboxIndex !== null && (
        <ArtifactLightbox
          artifacts={lightboxArtifacts}
          index={lightboxIndex}
          onIndexChange={setLightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Workspace />
    </ReactFlowProvider>
  );
}
