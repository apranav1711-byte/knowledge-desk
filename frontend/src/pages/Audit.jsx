import { useCallback, useEffect, useState } from 'react';
import { Fingerprint, Play, ShieldCheck } from 'lucide-react';
import { api, fmtDateTime, ROLE_LABEL } from '../api';
import { Badge, Card, Spinner } from '../components/ui';

const EVENTS = ['', 'query', 'document.upload', 'document.delete', 'document.reclassify', 'document.failed', 'document.download', 'user.create', 'user.update', 'security.check', 'acl.violation'];
const PAGE = 25;

export default function Audit({ notify }) {
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [event, setEvent] = useState('');
  const [verify, setVerify] = useState(null);
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState('');

  const load = useCallback(() => {
    api(`/admin/audit?limit=${PAGE}&offset=${offset}${event ? `&event=${encodeURIComponent(event)}` : ''}`)
      .then((r) => { setRows(r.items); setTotal(r.total); }).catch((e) => { notify(e.message, 'err'); setRows([]); });
  }, [offset, event, notify]);
  useEffect(() => { load(); }, [load]);

  const run = async (kind) => {
    setBusy(kind);
    try {
      if (kind === 'verify') setVerify(await api('/admin/audit/verify'));
      else { setCheck(await api('/admin/security-check', { method: 'POST' })); load(); }
    } catch (e) { notify(e.message, 'err'); } finally { setBusy(''); }
  };
  const summary = (r) => r.query || Object.entries(r.detail || {}).filter(([, v]) => v !== null && v !== '' && !Array.isArray(v)).slice(0, 3).map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`).join(' · ');

  return (
    <>
      <div className="page-head"><div><h1>Audit</h1></div></div>
      <div className="grid g2" style={{ marginBottom: 16 }}>
        <Card title="Audit chain integrity">
          {verify && <div className={`status-banner ${verify.tamper_free ? 'status-ok' : 'status-bad'}`} style={{ marginBottom: 12 }}><Fingerprint size={20} />
            <div><b>{verify.tamper_free ? 'No tampering detected' : `Chain broken at record #${verify.broken_seq}`}</b><div style={{ fontSize: 12.5 }}>{verify.records_checked} records checked{verify.reason ? ` · ${verify.reason}` : ''}</div></div></div>}
          <button className="btn btn-primary" onClick={() => run('verify')} disabled={busy === 'verify'}>{busy === 'verify' ? <Spinner /> : <ShieldCheck size={16} />} Verify audit chain</button>
          <p className="hint">Detects edited, reordered or missing records. It cannot detect deletion of the newest records without an external checkpoint.</p>
        </Card>
        <Card title="Access-control self-test">
          {check && <div className={`status-banner ${check.leaks === 0 ? 'status-ok' : 'status-bad'}`} style={{ marginBottom: 12 }}><ShieldCheck size={20} />
            <div><b>{check.leaks === 0 ? `0 leaks in ${check.trials} trials` : `${check.leaks} leak(s) in ${check.trials} trials`}</b><div style={{ fontSize: 12.5 }}>{check.documents_probed} documents × 4 roles</div></div></div>}
          {check?.failures?.map((f, i) => <p key={i} className="error-text">{ROLE_LABEL[f.role]} received {f.leaked_classifications.join(', ')} while probing “{f.document}”.</p>)}
          <button className="btn btn-primary" onClick={() => run('check')} disabled={busy === 'check'}>{busy === 'check' ? <Spinner /> : <Play size={16} />} Run security check</button>
          <p className="hint">Zero observed leaks is bounded evidence for this corpus, not a proof.</p>
        </Card>
      </div>
      <Card title="Activity log" action={<select style={{ width: 200 }} value={event} onChange={(e) => { setOffset(0); setEvent(e.target.value); }}>{EVENTS.map((x) => <option key={x} value={x}>{x || 'All events'}</option>)}</select>}>
        {!rows ? <Spinner /> : <div className="table-wrap"><table className="data">
          <thead><tr><th>#</th><th>When</th><th>User</th><th>Event</th><th>Details</th><th>Result</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id}><td className="muted">{r.seq}</td><td style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(r.created_at)}</td>
              <td><div>{r.user_email || '—'}</div><div className="cell-sub">{ROLE_LABEL[r.user_role] || r.user_role}</div></td>
              <td><Badge tone={r.event === 'acl.violation' ? 'red' : r.event === 'query' ? 'blue' : 'neutral'}>{r.event}</Badge></td>
              <td style={{ maxWidth: 380 }}>{summary(r)}</td>
              <td>{r.mode ? <Badge tone={r.mode === 'fallback' ? 'amber' : 'green'}>{r.mode === 'fallback' ? 'No evidence' : 'Answered'}</Badge> : '—'}</td></tr>))}
            {rows.length === 0 && <tr><td colSpan={6} className="muted" style={{ textAlign: 'center', padding: 28 }}>No events yet.</td></tr>}</tbody>
        </table></div>}
        <div className="toolbar" style={{ marginTop: 14, justifyContent: 'space-between' }}>
          <span className="muted">{total} event{total === 1 ? '' : 's'}</span>
          <span style={{ display: 'flex', gap: 8 }}><button className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button><button className="btn btn-sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</button></span>
        </div>
      </Card>
    </>
  );
}
