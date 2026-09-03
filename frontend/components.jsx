// VEDA shared UI primitives (M8-B).
//
// No imports/exports — this is a classic (non-module) Babel-transformed
// script, so everything here is a plain const/function in the global
// scope, available to screens.jsx and app.jsx which load after it (see
// index.html's script order). React/ReactDOM come from the UMD globals
// loaded before Babel runs.

const { useState, useEffect, useRef } = React;

// ─── design constants ──────────────────────────────────────────────────

const NAV_ITEMS = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'documents', label: 'Documents' },
  { id: 'activity', label: 'Activity' },
  { id: 'evidence', label: 'Evidence & Deliverable' },
];

// Every status string that can actually appear (DocumentInfo.status,
// TaskStatusResponse.status, ActivityStep.success) mapped to one of
// three semantic tones. Anything not listed falls back to neutral
// rather than guessing — see StatusPill.
const STATUS_TONE = {
  indexed: 'ok', completed: 'ok', ready: 'ok',
  failed: 'warn', unavailable: 'warn', incomplete: 'warn', blocked: 'warn',
  queued: 'neutral', running: 'neutral', processing: 'neutral',
};

const TONE_CLASSES = {
  ok:      'bg-ok/10 text-ok border-ok/20',
  warn:    'bg-warn/10 text-warn border-warn/20',
  neutral: 'bg-black/5 text-muted border-line',
};

// ─── primitives ─────────────────────────────────────────────────────────

function Card({ children, className = '', dark = false }) {
  return (
    <div className={
      (dark
        ? 'bg-ink text-white border-ink '
        : 'bg-surface text-text border-line ') +
      'border rounded-xl ' + className
    }>
      {children}
    </div>
  );
}

function LabelMicro({ children, className = '' }) {
  return <div className={'label-micro ' + className}>{children}</div>;
}

function StatusPill({ status }) {
  const tone = STATUS_TONE[status] || 'neutral';
  return (
    <span className={
      'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium uppercase tracking-wide ' +
      TONE_CLASSES[tone]
    }>
      <span className={
        'w-1.5 h-1.5 rounded-full ' +
        (tone === 'ok' ? 'bg-ok' : tone === 'warn' ? 'bg-warn' : 'bg-muted')
      } />
      {status}
    </span>
  );
}

function StatBlock({ label, value, sub, dark = false }) {
  return (
    <Card dark={dark} className="p-5 flex flex-col gap-2 min-w-[150px]">
      <LabelMicro className={dark ? 'text-white/50' : ''}>{label}</LabelMicro>
      <div className="text-4xl font-semibold tracking-tight font-mono truncate">{value}</div>
      {sub && <div className={'text-xs ' + (dark ? 'text-white/60' : 'text-muted')}>{sub}</div>}
    </Card>
  );
}

function EmptyState({ children }) {
  return (
    <div className="flex items-center justify-center text-sm text-muted py-16 border border-dashed border-line rounded-xl">
      {children}
    </div>
  );
}

function Dots() {
  // Deliberately not a spinner graphic — three static dots with a slow
  // opacity pulse via Tailwind's built-in `animate-pulse`, matching the
  // brief's "subtle and functional, not theatrical" motion guidance.
  return (
    <span className="inline-flex gap-1 animate-pulse" aria-label="loading">
      <span className="w-1.5 h-1.5 rounded-full bg-muted" />
      <span className="w-1.5 h-1.5 rounded-full bg-muted" />
      <span className="w-1.5 h-1.5 rounded-full bg-muted" />
    </span>
  );
}

// ─── shell: top bar, nav rail, bottom status strip ──────────────────────

function TopBar({ status }) {
  const sovereign = status?.sovereign_mode;
  return (
    <header className="h-16 shrink-0 border-b border-line flex items-center justify-between px-6 bg-surface">
      <div className="flex items-baseline gap-3">
        <span className="text-lg font-bold tracking-tight">VEDA</span>
        <span className="text-xs text-muted hidden sm:inline">Sovereign Industrial AI Workbench</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={
          'w-2 h-2 rounded-full ' + (sovereign ? 'bg-ok' : 'bg-muted')
        } />
        <span className="label-micro">
          {status ? (sovereign ? 'Sovereign Mode' : 'Standard Mode') : <Dots />}
        </span>
      </div>
    </header>
  );
}

function NavRail({ active, onSelect, docCount, taskStatus }) {
  const badge = { documents: docCount > 0 ? docCount : null, activity: taskStatus === 'running' ? '●' : null };
  return (
    <nav className="w-52 shrink-0 border-r border-line bg-surface flex flex-col p-3 gap-1">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item.id)}
          className={
            'text-left px-3 py-2.5 rounded-lg text-sm font-medium flex items-center justify-between transition-colors ' +
            (active === item.id ? 'bg-ink text-white' : 'text-text hover:bg-black/5')
          }
        >
          <span>{item.label}</span>
          {badge[item.id] && (
            <span className={
              'text-[10px] font-mono ' + (active === item.id ? 'text-white/70' : 'text-muted')
            }>{badge[item.id]}</span>
          )}
        </button>
      ))}
    </nav>
  );
}

function BottomStatusBar({ status, model }) {
  const item = (label, value, tone) => (
    <div className="flex items-center gap-2">
      <span className="label-micro">{label}</span>
      <span className={
        'text-xs font-medium ' +
        (tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : 'text-text')
      }>{value}</span>
    </div>
  );
  return (
    <footer className="h-10 shrink-0 border-t border-line bg-surface flex items-center gap-8 px-6">
      {item('Model', model ? (model.status === 'ready' ? `${model.active_model} · LOCAL` : 'Unavailable') : '—',
            model ? (model.status === 'ready' ? 'ok' : 'warn') : null)}
      {item('Knowledge', 'Local')}
      {item('Network', !status ? '—' : (status.sovereign_mode ? 'Protected' : 'Unrestricted'),
            !status ? null : (status.sovereign_mode ? 'ok' : 'warn'))}
    </footer>
  );
}
