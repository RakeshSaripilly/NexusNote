import { useMemo, useState } from 'react';
import {
  ChevronDown,
  ExternalLink,
  FileText,
  ImageIcon,
  ListTree,
  Loader2,
  Quote,
  X,
} from 'lucide-react';
import { resolveAssetUrl } from '../api/client';

const TABS = [
  { id: 'facts', label: 'Facts & Sources', icon: ListTree },
  { id: 'artifacts', label: 'Visual Artifacts', icon: ImageIcon },
];

/** A single click-to-expand citation pill. */
function CitationPill({ source }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs text-slate-300 transition-colors hover:text-slate-100"
      >
        <FileText size={12} className="shrink-0 text-slate-500" />
        <span className="min-w-0 flex-1 truncate">
          {source.file_name}
          {source.location_tag ? ` • ${source.location_tag}` : ''}
        </span>
        <ChevronDown
          size={13}
          className={`shrink-0 text-slate-500 transition-transform duration-200 ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {open && source.raw_snippet && (
        <div className="border-t border-slate-800 px-2.5 py-2">
          <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <Quote size={10} /> Original snippet
          </p>
          <p className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-400">
            {source.raw_snippet}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * Right-hand slide-out panel showing deep source lineage for the selected
 * concept: synthesized facts with expandable citations, and an artifact gallery.
 */
export default function ProvenanceDrawer({
  open,
  concept,
  loading,
  error,
  onClose,
  onOpenArtifact,
}) {
  const [tab, setTab] = useState('facts');

  const facts = concept?.facts ?? [];
  const artifacts = concept?.artifacts ?? [];

  const sourceFiles = useMemo(() => {
    const unique = new Map();
    facts.forEach((fact) => {
      (fact.sources ?? []).forEach((source) => {
        if (source.file_name && !unique.has(source.file_name)) {
          unique.set(source.file_name, source.location_tag || '');
        }
      });
    });
    return Array.from(unique, ([file, tag]) => ({ file, tag }));
  }, [facts]);

  if (!open) return null;

  return (
    <aside
      className="absolute inset-y-0 right-0 z-20 flex w-[480px] animate-slide-in-right flex-col border-l border-slate-800 bg-slate-950/95 shadow-2xl backdrop-blur"
      aria-label="Concept provenance"
    >
      <header className="flex items-start gap-3 border-b border-slate-800 px-5 py-4">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-cyan-500">
            Concept lineage
          </p>
          <h2 className="mt-1 break-words text-base font-semibold text-slate-100">
            {loading ? 'Loading…' : concept?.title || 'Untitled Concept'}
          </h2>

          {!loading && concept && (
            <p className="mt-1 text-xs text-slate-500">
              {facts.length} fact{facts.length === 1 ? '' : 's'}
              {' · '}
              {sourceFiles.length} source document{sourceFiles.length === 1 ? '' : 's'}
              {' · '}
              {artifacts.length} artifact{artifacts.length === 1 ? '' : 's'}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          title="Close panel"
          className="shrink-0 rounded-lg border border-slate-700 p-2 text-slate-400 transition-colors hover:border-red-500/60 hover:text-red-300"
        >
          <X size={16} />
        </button>
      </header>

      <nav className="flex gap-1 border-b border-slate-800 px-3 py-2">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
              tab === id
                ? 'bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-500/30'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <Icon size={13} />
            {label}
            <span className="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
              {id === 'facts' ? facts.length : artifacts.length}
            </span>
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {loading && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
            <Loader2 size={16} className="animate-spin" />
            Tracing provenance…
          </div>
        )}

        {!loading && error && (
          <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}

        {!loading && !error && tab === 'facts' && (
          <div className="space-y-3">
            {facts.length === 0 && (
              <p className="py-16 text-center text-sm text-slate-500">
                No synthesized facts for this concept yet.
              </p>
            )}

            {facts.map((fact) => (
              <article
                key={fact.fact_id}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 transition-colors hover:border-slate-700"
              >
                <p className="flex gap-2 text-sm leading-relaxed text-slate-200">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />
                  <span>{fact.text}</span>
                </p>

                {(fact.sources ?? []).length > 0 && (
                  <div className="mt-3 space-y-1.5 pl-3.5">
                    {fact.sources.map((source, index) => (
                      <CitationPill
                        key={`${fact.fact_id}-${index}`}
                        source={source}
                      />
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}

        {!loading && !error && tab === 'artifacts' && (
          <div>
            {artifacts.length === 0 ? (
              <p className="py-16 text-center text-sm text-slate-500">
                No visual artifacts extracted for this concept.
                <span className="mt-2 block text-xs text-slate-600">
                  Diagrams larger than 150x150 px are pulled from source pages.
                </span>
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {artifacts.map((artifact, index) => (
                  <button
                    key={artifact.id}
                    type="button"
                    onClick={() => onOpenArtifact(index)}
                    className="group overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 text-left transition-colors hover:border-cyan-500/50"
                  >
                    <div className="flex h-28 items-center justify-center overflow-hidden bg-slate-950/70 p-2">
                      <img
                        src={resolveAssetUrl(artifact.image_url)}
                        alt={artifact.caption || artifact.file_name || 'Diagram'}
                        loading="lazy"
                        className="max-h-full max-w-full object-contain transition-transform duration-200 group-hover:scale-105"
                      />
                    </div>
                    <div className="border-t border-slate-800 px-2.5 py-2">
                      <p className="flex items-center gap-1 truncate text-[11px] font-medium text-slate-300">
                        {artifact.caption || 'Diagram'}
                        <ExternalLink
                          size={10}
                          className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                        />
                      </p>
                      <p className="mt-0.5 truncate text-[10px] text-slate-500">
                        {artifact.file_name}
                        {artifact.location_tag ? ` • ${artifact.location_tag}` : ''}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}