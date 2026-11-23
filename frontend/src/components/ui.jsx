import { useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';
import { labelClass, ROLE_LABEL } from '../api';

export const Spinner = ({ size = 16 }) => <Loader2 size={size} className="spin" aria-hidden />;

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

const CLASS_TONE = { Public: 'green', General_Internal: 'blue', Management: 'violet', HR_Confidential: 'amber', Restricted: 'red' };
export const ClassBadge = ({ value }) => <Badge tone={CLASS_TONE[value] || 'neutral'}>{labelClass(value)}</Badge>;

const STATUS_TONE = { ready: 'green', processing: 'blue', failed: 'red', retired: 'neutral' };
export const StatusBadge = ({ value }) => (
  <Badge tone={STATUS_TONE[value] || 'neutral'}>{value === 'processing' ? <><Spinner size={11} /> Indexing</> : value[0].toUpperCase() + value.slice(1)}</Badge>
);
export const RoleBadge = ({ value }) => <Badge tone={{ admin: 'red', hr: 'amber', manager: 'violet', employee: 'blue' }[value] || 'neutral'}>{ROLE_LABEL[value] || value}</Badge>;

export function Modal({ title, onClose, children, wide, footer }) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="modal-body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  );
}

export function Card({ title, subtitle, action, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && <header className="card-head"><div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>{action}</header>}
      {children}
    </section>
  );
}

export const Stat = ({ icon: Icon, label, value, hint, tone = 'blue' }) => (
  <div className="stat">
    <span className={`stat-icon tone-${tone}`}><Icon size={18} /></span>
    <div><p className="stat-label">{label}</p><p className="stat-value">{value}</p>{hint && <p className="stat-hint">{hint}</p>}</div>
  </div>
);

export const Empty = ({ icon: Icon, title, children }) => (
  <div className="empty">{Icon && <Icon size={28} />}<h4>{title}</h4><p>{children}</p></div>
);

export function Toast({ toast, onDone }) {
  useEffect(() => { if (!toast) return; const t = setTimeout(onDone, 4500); return () => clearTimeout(t); }, [toast, onDone]);
  if (!toast) return null;
  return <div className={`toast toast-${toast.tone || 'ok'}`} role="status">{toast.text}</div>;
}

/** Renders answer/excerpt text: Markdown tables become real tables; [C1] markers become citation buttons. */
const splitCells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
const isSeparator = (l) => splitCells(l).every((c) => /^:?-{2,}:?$/.test(c));

export function RichText({ text, onCite }) {
  const blocks = [];
  let table = [];
  const flush = () => { if (table.length) { blocks.push({ t: 'table', rows: table }); table = []; } };
  for (const line of (text || '').split('\n')) {
    if (line.trim().startsWith('|')) { if (!isSeparator(line)) table.push(line); }
    else { flush(); if (line.trim()) blocks.push({ t: 'p', text: line }); }
  }
  flush();
  const cite = (s) => s.split(/(\[C\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(C\d+)\]$/);
    return m ? <button key={i} className="cite" onClick={() => onCite?.(m[1])}>{m[1]}</button> : part;
  });
  return (
    <>
      {blocks.map((b, i) => (b.t === 'p'
        ? <p key={i}>{cite(b.text)}</p>
        : (
          <div className="table-wrap" key={i}>
            <table className="mini-table">
              <thead><tr>{splitCells(b.rows[0]).map((c, j) => <th key={j}>{c}</th>)}</tr></thead>
              <tbody>{b.rows.slice(1).map((r, k) => <tr key={k}>{splitCells(r).map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )))}
    </>
  );
}
