import { useEffect, useState } from 'react';
import { Check, FileText, Layers, Lock, MessageSquareText, Search, ShieldCheck } from 'lucide-react';
import { api, CLASSIFICATIONS, fmtDate, fmtDateTime, labelClass } from '../api';
import { Badge, Card, ClassBadge, Empty, Spinner, Stat } from '../components/ui';

export default function Overview({ me, go }) {
  const [docs, setDocs] = useState(null);
  const [history, setHistory] = useState(null);
  const [q, setQ] = useState('');
  useEffect(() => {
    api('/documents').then(setDocs).catch(() => setDocs([]));
    api('/chat/history').then(setHistory).catch(() => setHistory([]));
  }, []);
  const ready = (docs || []).filter((d) => d.status === 'ready');
  const passages = ready.reduce((n, d) => n + d.total_chunks, 0);
  const first = (me.full_name || me.email).split(' ')[0];

  return (
    <>
      <div className="page-head">
        <div><h1>Welcome back, {first}</h1><p>Search company policy with evidence for every answer. You see only what your role is cleared for.</p></div>
      </div>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat icon={FileText} label="Documents available" value={docs ? ready.length : '…'} hint="Cleared for your role" tone="blue" />
        <Stat icon={Layers} label="Searchable passages" value={docs ? passages.toLocaleString() : '…'} hint="Indexed from your documents" tone="teal" />
        <Stat icon={MessageSquareText} label="Questions asked" value={history ? history.length : '…'} hint="Your recent history" tone="violet" />
        <Stat icon={ShieldCheck} label="Clearance levels" value={`${me.can_read.length} of ${CLASSIFICATIONS.length}`} hint="Document classifications" tone="amber" />
      </div>

      <div className="grid g-2-1">
        <div className="grid" style={{ alignContent: 'start' }}>
          <Card title="Ask a question" subtitle="Answers quote the source passage and show where it came from.">
            <form className="composer" style={{ border: 0, paddingTop: 0 }} onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) go('assistant', { q: q.trim() }); }}>
              <div className="search" style={{ maxWidth: 'none' }}><Search size={16} /><input type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. How many annual leave days do employees get?" /></div>
              <button className="btn btn-teal">Search</button>
            </form>
          </Card>
          <div className="grid g2">
            <Card title="Recent questions">
              {!history ? <Spinner /> : history.length === 0 ? <Empty icon={MessageSquareText} title="No questions yet">Your questions will appear here.</Empty> :
                history.slice(0, 6).map((h) => (
                  <div className="list-row" key={h.id}><button className="link-btn" style={{ textAlign: 'left' }} onClick={() => go('assistant', { q: h.query })}>{h.query}</button><span className="muted" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{fmtDateTime(h.created_at)}</span></div>
                ))}
            </Card>
            <Card title="Recently added documents" action={<button className="link-btn" onClick={() => go('documents')}>View all</button>}>
              {!docs ? <Spinner /> : ready.length === 0 ? <Empty icon={FileText} title="No documents yet">Documents appear here once uploaded and indexed.</Empty> :
                ready.slice(0, 6).map((d) => (
                  <div className="list-row" key={d.id}><div><div className="cell-title">{d.title}</div><div className="cell-sub">{fmtDate(d.created_at)} · {d.file_type.toUpperCase()}</div></div><ClassBadge value={d.classification} /></div>
                ))}
            </Card>
          </div>
        </div>
        <Card title="Your access" subtitle="What your role can search">
          {CLASSIFICATIONS.map((c) => {
            const ok = me.can_read.includes(c);
            return <div key={c} className={`access-row ${ok ? '' : 'denied'}`}>{ok ? <Check size={16} color="#16a34a" /> : <Lock size={16} />}<span style={{ flex: 1 }}>{labelClass(c)}</span>{ok ? <Badge tone="green">Allowed</Badge> : <Badge>No access</Badge>}</div>;
          })}
          <p className="hint" style={{ marginTop: 12 }}>Restricted documents are never retrieved for your searches, even indirectly.</p>
        </Card>
      </div>
    </>
  );
}
