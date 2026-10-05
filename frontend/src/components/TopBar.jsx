import { useCallback, useMemo, useRef, useState } from 'react';
import { useReactFlow } from '@xyflow/react';
import {
  AlertTriangle,
  CheckCircle2,
  LayoutGrid,
  Loader2,
  Search,
  Upload,
  X,
} from 'lucide-react';

const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md', '.png', '.jpg', '.jpeg', '.webp', '.bmp'];

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

/** Drag-and-drop + file-picker upload modal with progress and ingest summary. */
function UploadModal({ open, onClose, onUpload }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const busy = progress !== null;

  const reset = useCallback(() => {
    setFile(null);
    setProgress(null);
    setError('');
    setResult(null);
    if (inputRef.current) inputRef.current.value = '';
  }, []);

  const close = useCallback(() => {
    if (busy) return;
    reset();
    onClose();
  }, [busy, reset, onClose]);

  const pickFile = useCallback((candidate) => {
    if (!candidate) return;
    const dot = candidate.name.lastIndexOf('.');
    const extension = dot >= 0 ? candidate.name.slice(dot).toLowerCase() : '';
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      setError(`Unsupported file type "${extension || 'unknown'}". Allowed: ${ACCEPTED_EXTENSIONS.join(', ')}`);
      return;
    }
    setError('');
    setResult(null);
    setFile(candidate);
  }, []);

  const submit = useCallback(async () => {
    if (!file) return;
    setError('');
    setResult(null);
    setProgress(0);
    try {
      const summary = await onUpload(file, setProgress);
      setResult(summary);
      setProgress(null);
    } catch (uploadError) {
      setProgress(null);
      setError(uploadError.message || 'Upload failed.');
    }
  }, [file, onUpload]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex animate-fade-in items-center justify-center bg-slate-950/80 p-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Upload document"
      onClick={close}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Ingest a document</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              PDF, TXT, MD or image — text is chunked, merged and grounded.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="rounded-lg border border-slate-700 p-2 text-slate-400 transition-colors hover:text-white disabled:opacity-40"
          >
            <X size={16} />
          </button>
        </header>

        <div className="space-y-4 px-5 py-5">
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              pickFile(event.dataTransfer.files?.[0]);
            }}
            onClick={() => !busy && inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              dragging
                ? 'border-cyan-400 bg-cyan-500/10'
                : 'border-slate-700 bg-slate-950/50 hover:border-slate-500'
            } ${busy ? 'pointer-events-none opacity-60' : ''}`}
          >
            <Upload size={26} className="text-slate-500" />
            <p className="mt-3 text-sm text-slate-300">
              {file ? file.name : 'Drop a file here, or click to browse'}
            </p>
            {file && (
              <p className="mt-1 text-xs text-slate-500">{formatBytes(file.size)}</p>
            )}
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(',')}
              className="hidden"
              onChange={(event) => pickFile(event.target.files?.[0])}
            />
          </div>

          {progress !== null && (
            <div>
              <div className="mb-1.5 flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1.5">
                  <Loader2 size={12} className="animate-spin" />
                  Uploading
                </span>
                <span>{progress}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-cyan-500 transition-[width] duration-200"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                Extracting artifacts, embedding chunks and merging into the graph…
              </p>
            </div>
          )}

          {error && (
            <p className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              {error}
            </p>
          )}

          {result && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-3 text-xs text-emerald-200">
              <p className="flex items-center gap-2 font-medium">
                <CheckCircle2 size={14} />
                {result.file_name} ingested
              </p>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-emerald-200/80">
                <div className="flex justify-between">
                  <dt>Chunks</dt>
                  <dd className="font-medium">{result.chunks_processed}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Artifacts</dt>
                  <dd className="font-medium">{result.artifacts_extracted}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>New concepts</dt>
                  <dd className="font-medium">{result.actions.created}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Extended</dt>
                  <dd className="font-medium">{result.actions.extended}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Merged sources</dt>
                  <dd className="font-medium">{result.actions.merged}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Sub-topics</dt>
                  <dd className="font-medium">{result.actions.spun_off}</dd>
                </div>
              </dl>
            </div>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-slate-800 px-5 py-4">
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 transition-colors hover:bg-slate-800 disabled:opacity-40"
          >
            {result ? 'Done' : 'Cancel'}
          </button>
          {!result && (
            <button
              type="button"
              onClick={submit}
              disabled={!file || busy}
              className="rounded-lg bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition-colors hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? 'Processing…' : 'Ingest'}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

/** Application header: branding, upload trigger, search and Dagre relayout. */
export default function TopBar({ nodes, onUpload, onRelayout }) {
  const { fitView } = useReactFlow();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(null);

  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (term.length < 2) return [];
    return nodes
      .filter((node) => (node.data?.label ?? '').toLowerCase().includes(term))
      .slice(0, 6);
  }, [nodes, query]);

  const focus = useCallback(
    (nodeId) => {
      setFocused(nodeId);
      fitView({ nodes: [{ id: nodeId }], padding: 0.6, duration: 500, maxZoom: 1.2 });
    },
    [fitView],
  );

  return (
    <>
      <header className="z-10 flex items-center gap-4 border-b border-slate-800 bg-slate-950/80 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <span className="rounded-lg bg-cyan-500/15 p-1.5 text-cyan-400">
            <LayoutGrid size={16} strokeWidth={2.4} />
          </span>
          <div>
            <h1 className="text-sm font-semibold leading-none text-slate-100">
              NexusNote
            </h1>
            <p className="mt-1 text-[10px] uppercase tracking-widest text-slate-500">
              GraphRAG synthesizer
            </p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search concepts…"
              className="w-56 rounded-lg border border-slate-700 bg-slate-900 py-2 pl-9 pr-3 text-xs text-slate-200 placeholder:text-slate-500 outline-none transition-colors focus:border-cyan-500/60"
            />
            {results.length > 0 && (
              <ul className="absolute right-0 z-30 mt-1 w-64 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 shadow-xl">
                {results.map((node) => (
                  <li key={node.id}>
                    <button
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        focus(node.id);
                        setQuery('');
                      }}
                      className={`block w-full truncate px-3 py-2 text-left text-xs transition-colors hover:bg-slate-800 ${
                        focused === node.id ? 'bg-slate-800 text-cyan-300' : 'text-slate-300'
                      }`}
                    >
                      {node.data?.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <button
            type="button"
            onClick={onRelayout}
            disabled={!nodes.length}
            title="Re-run the Dagre auto-layout"
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 transition-colors hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <LayoutGrid size={13} />
            Relayout
          </button>

          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-cyan-500 px-3.5 py-2 text-xs font-semibold text-slate-950 transition-colors hover:bg-cyan-400"
          >
            <Upload size={13} strokeWidth={2.5} />
            Upload
          </button>
        </div>
      </header>

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUpload={onUpload}
      />
    </>
  );
}
