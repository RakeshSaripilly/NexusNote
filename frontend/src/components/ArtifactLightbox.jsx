import { useCallback, useEffect } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  X,
} from 'lucide-react';
import { resolveAssetUrl } from '../api/client';

/**
 * Fullscreen viewer for extracted diagrams, with keyboard navigation across the
 * supplied artifact list.
 */
export default function ArtifactLightbox({
  artifacts = [],
  index,
  onClose,
  onIndexChange,
}) {
  const artifact = artifacts[index];
  const total = artifacts.length;

  const goPrev = useCallback(() => {
    if (total > 1) onIndexChange((index - 1 + total) % total);
  }, [index, total, onIndexChange]);

  const goNext = useCallback(() => {
    if (total > 1) onIndexChange((index + 1) % total);
  }, [index, total, onIndexChange]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'ArrowLeft') goPrev();
      if (event.key === 'ArrowRight') goNext();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, goPrev, goNext]);

  if (!artifact) return null;

  const src = resolveAssetUrl(artifact.image_url);

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in flex-col bg-slate-950/95 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={artifact.caption || 'Artifact viewer'}
    >
      <header className="flex items-start gap-4 border-b border-slate-800 px-6 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-slate-100">
            {artifact.caption || 'Visual artifact'}
          </h2>
          <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-slate-400">
            <FileText size={12} />
            {artifact.file_name}
            {artifact.location_tag ? ` · ${artifact.location_tag}` : ''}
          </p>
        </div>

        <span className="shrink-0 self-center rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">
          {index + 1} / {total}
        </span>

        <a
          href={src}
          download
          title="Download original"
          className="shrink-0 self-center rounded-lg border border-slate-700 p-2 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
        >
          <Download size={16} />
        </a>

        <button
          type="button"
          onClick={onClose}
          title="Close (Esc)"
          className="shrink-0 self-center rounded-lg border border-slate-700 p-2 text-slate-300 transition-colors hover:border-red-500/60 hover:text-red-300"
        >
          <X size={16} />
        </button>
      </header>

      <div className="relative flex flex-1 items-center justify-center overflow-auto p-6">
        {total > 1 && (
          <button
            type="button"
            onClick={goPrev}
            title="Previous (left arrow)"
            className="absolute left-4 z-10 rounded-full border border-slate-700 bg-slate-900/80 p-3 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
          >
            <ChevronLeft size={20} />
          </button>
        )}

        <img
          src={src}
          alt={artifact.caption || artifact.file_name || 'Extracted diagram'}
          className="max-h-full max-w-full rounded-lg border border-slate-800 bg-slate-900 object-contain shadow-2xl"
        />

        {total > 1 && (
          <button
            type="button"
            onClick={goNext}
            title="Next (right arrow)"
            className="absolute right-4 z-10 rounded-full border border-slate-700 bg-slate-900/80 p-3 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
          >
            <ChevronRight size={20} />
          </button>
        )}
      </div>
    </div>
  );
}
