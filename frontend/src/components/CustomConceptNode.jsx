import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ImageIcon, Lightbulb } from 'lucide-react';

/**
 * Graph card for a :Concept node — shows the topic title plus badges for the
 * number of synthesized facts and extracted visual artifacts.
 */
function CustomConceptNode({ data, selected }) {
  const { label = 'Untitled Concept', factCount = 0, artifactCount = 0 } = data || {};

  return (
    <div
      className={[
        'w-[260px] rounded-xl border bg-slate-900/90 px-4 py-3 shadow-lg backdrop-blur',
        'transition-all duration-200',
        selected
          ? 'border-cyan-400 shadow-cyan-500/20 ring-1 ring-cyan-400/40'
          : 'border-slate-700 hover:border-slate-500 hover:bg-slate-900',
      ].join(' ')}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !border-slate-900 !bg-slate-500"
      />

      <div className="flex items-start gap-2">
        <span className="mt-0.5 rounded-md bg-cyan-500/15 p-1 text-cyan-400">
          <Lightbulb size={14} strokeWidth={2.2} />
        </span>
        <p className="flex-1 break-words text-sm font-semibold leading-snug text-slate-100">
          {label}
        </p>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <span
          title={`${factCount} synthesized fact${factCount === 1 ? '' : 's'}`}
          className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/80 px-2 py-0.5 text-[11px] font-medium text-slate-300"
        >
          {factCount} fact{factCount === 1 ? '' : 's'}
        </span>

        {artifactCount > 0 && (
          <span
            title={`${artifactCount} visual artifact${artifactCount === 1 ? '' : 's'}`}
            className="inline-flex items-center gap-1 rounded-full border border-violet-500/40 bg-violet-500/15 px-2 py-0.5 text-[11px] font-medium text-violet-300"
          >
            <ImageIcon size={11} strokeWidth={2.4} />
            {artifactCount}
          </span>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !border-slate-900 !bg-slate-500"
      />
    </div>
  );
}

export default memo(CustomConceptNode);
