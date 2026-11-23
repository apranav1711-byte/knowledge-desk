import { useEffect, useRef, useState } from 'react';
import { ExternalLink, FileSearch, Send, ThumbsDown, ThumbsUp } from 'lucide-react';
import { api } from '../api';
import { Badge, Card, ClassBadge, Empty, Modal, RichText, Spinner } from '../components/ui';

const STARTERS = ['How many annual leave days do employees get?', 'What is the remote work policy?', 'What are the travel expense limits?'];

export function DocViewer({ source, onClose }) {
  const [doc, setDoc] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => { api(`/documents/${source.document_id}`).then(setDoc).catch((e) => setErr(e.message)); }, [source.document_id]);
  return (
    <Modal wide title={doc?.title || source.title} onClose={onClose}>
      {err ? <p className="error-text">{err}</p> : !doc ? <Spinner /> : (
        <>
          <p className="muted" style={{ marginBottom: 14 }}>{doc.total_pages} page(s) · {doc.total_chunks} passages · the passage used for the answer is highlighted</p>
          {doc.excerpts.map((x) => (
            <div key={x.chunk_index} className={`excerpt-block ${x.content === source.excerpt ? 'active' : ''}`}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Page {x.page}{x.section ? ` · ${x.section}` : ''}</div>
              <RichText text={x.content} />
            </div>
          ))}
        </>
      )}
    </Modal>
  );
}

export default function Assistant({ arg, notify }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const [viewing, setViewing] = useState(null);
  const bottom = useRef(null);
  const started = useRef(false);

  const ask = async (text) => {
    const query = (text ?? input).trim();
    if (query.length < 3 || busy) return;
    const id = crypto.randomUUID();
    setInput(''); setBusy(true);
    setMessages((m) => [...m, { id: id + 'q', role: 'user', text: query }]);
    try {
      const r = await api('/chat/query', { method: 'POST', body: { query } });
      setMessages((m) => [...m, { id, role: 'bot', ...r }]); setSelected(id);
    } catch (e) {
      setMessages((m) => [...m, { id, role: 'bot', error: e.message, sources: [] }]);
    } finally { setBusy(false); }
  };
  useEffect(() => { if (arg?.q && !started.current) { started.current = true; ask(arg.q); } }, []); // eslint-disable-line
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, busy]);

  const rate = async (m, rating) => {
    setMessages((x) => x.map((y) => (y.id === m.id ? { ...y, rating } : y)));
    try { await api('/feedback', { method: 'POST', body: { audit_id: m.audit_id, rating } }); notify('Thanks for the feedback'); }
    catch (e) { notify(e.message, 'err'); }
  };
  const active = messages.find((m) => m.id === selected);

  return (
    <>
      <div className="page-head"><div><h1>Ask the assistant</h1><p>Answers are assembled only from passages your role may read, and each one cites its source.</p></div></div>
      <div className="assistant">
        <Card className="chat">
          <div className="messages" aria-live="polite">
            {messages.length === 0 && (
              <Empty icon={FileSearch} title="Start with a policy question">
                Ask about a policy, allowance, limit, or procedure.
                <span className="chips" style={{ justifyContent: 'center', marginTop: 12 }}>{STARTERS.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</span>
              </Empty>
            )}
            {messages.map((m) => m.role === 'user' ? <div key={m.id} className="msg-user">{m.text}</div> : (
              <div key={m.id} className={`msg-bot ${selected === m.id ? 'selected' : ''}`} onClick={() => setSelected(m.id)}>
                {m.error ? <p className="error-text">{m.error}</p> : <RichText text={m.answer} onCite={(c) => { setSelected(m.id); document.getElementById(`src-${c}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }} />}
                {!m.error && (
                  <div className="msg-meta">
                    <Badge tone={m.mode === 'fallback' ? 'amber' : 'green'}>{m.mode === 'fallback' ? 'Insufficient evidence' : 'Evidence-backed'}</Badge>
                    <span>{m.telemetry.total_ms} ms</span>
                    <span style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
                      <button className="icon-btn" aria-label="Helpful" onClick={(e) => { e.stopPropagation(); rate(m, 1); }}><ThumbsUp size={15} color={m.rating === 1 ? '#16a34a' : undefined} /></button>
                      <button className="icon-btn" aria-label="Not helpful" onClick={(e) => { e.stopPropagation(); rate(m, -1); }}><ThumbsDown size={15} color={m.rating === -1 ? '#dc2626' : undefined} /></button>
                    </span>
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="msg-bot"><Spinner /> Searching documents available to your role…</div>}
            <div ref={bottom} />
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(); }}>
            <textarea rows={2} maxLength={500} placeholder="Ask about a company policy…" value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }} />
            <button className="btn btn-teal" disabled={busy || input.trim().length < 3}><Send size={16} /> Ask</button>
          </form>
        </Card>

        <Card title="Evidence" subtitle={active ? 'Source passages behind the selected answer' : 'Select an answer to see its sources'}>
          {!active || active.error ? <Empty icon={FileSearch} title="No evidence selected">Sources appear here after you ask a question.</Empty>
            : active.sources.length === 0 ? <Empty title="No supporting passage">Nothing in the documents available to your role supports this question.</Empty>
            : active.sources.map((s) => (
              <div className="source" id={`src-${s.id}`} key={s.id}>
                <header><div><strong>[{s.id}] {s.title}</strong><div className="muted" style={{ fontSize: 12 }}>Page {s.page}{s.section ? ` · ${s.section}` : ''}</div></div><ClassBadge value={s.classification} /></header>
                <div className="excerpt"><RichText text={s.excerpt} /></div>
                <div className="meta"><span title="Retrieval similarity, not factual certainty">Similarity {s.score.toFixed(2)}</span><button className="link-btn" onClick={() => setViewing(s)}>Open document <ExternalLink size={12} /></button></div>
              </div>
            ))}
          {active && !active.error && (
            <details style={{ marginTop: 8 }}><summary className="muted" style={{ cursor: 'pointer' }}>Retrieval details</summary>
              <p className="hint">Role: {active.telemetry.role} · candidates: {active.telemetry.candidates} · embedding {active.telemetry.embedding_ms} ms · retrieval {active.telemetry.retrieval_ms} ms</p>
              <p className="hint">{active.telemetry.retrieval}. Answer stage: {active.telemetry.answer_stage}. Audit ID: {active.audit_id.slice(0, 8)}</p>
            </details>
          )}
        </Card>
      </div>
      {viewing && <DocViewer source={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}
