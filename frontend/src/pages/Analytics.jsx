import { useEffect, useState } from 'react';
import { CheckCircle2, Clock, FileText, Layers, MessageSquareText, ShieldAlert, ThumbsUp, Users } from 'lucide-react';
import { api, labelClass, ROLE_LABEL } from '../api';
import { Card, Empty, Spinner, Stat } from '../components/ui';

function HBars({ rows, label }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return rows.length === 0 ? <p className="muted">No data yet.</p> : rows.map((r) => (
    <div className="hbar" key={r.key}><span>{label(r)}</span><div className="track"><div className="fill" style={{ width: `${(r.count / max) * 100}%` }} /></div><span className="num">{r.count}</span></div>
  ));
}

export default function Analytics({ notify }) {
  const [d, setD] = useState(null);
  useEffect(() => { api('/admin/analytics').then(setD).catch((e) => notify(e.message, 'err')); }, [notify]);
  if (!d) return <Spinner size={22} />;
  const k = d.kpis;
  const maxDay = Math.max(1, ...d.timeseries.map((x) => x.answered + x.fallback));
  const docsByClass = Object.entries(d.documents.filter((x) => x.status === 'ready').reduce((a, x) => ({ ...a, [x.classification]: (a[x.classification] || 0) + x.count }), {})).map(([key, count]) => ({ key, count }));
  const docsByStatus = Object.entries(d.documents.reduce((a, x) => ({ ...a, [x.status]: (a[x.status] || 0) + x.count }), {}));
  const usersByRole = Object.entries(d.users.filter((u) => u.active).reduce((a, u) => ({ ...a, [u.role]: (a[u.role] || 0) + u.count }), {})).map(([key, count]) => ({ key, count }));
  const totalDocs = d.documents.reduce((n, x) => n + x.count, 0);

  return (
    <>
      <div className="page-head"><div><h1>Analytics</h1></div></div>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat icon={MessageSquareText} label="Questions (30 days)" value={k.queries_30d} hint={`${k.queries_24h} in the last 24 h`} tone="blue" />
        <Stat icon={CheckCircle2} label="Answer rate" value={k.answer_rate == null ? '—' : `${Math.round(k.answer_rate * 100)}%`} hint={`${k.fallback_30d} insufficient-evidence`} tone="green" />
        <Stat icon={Clock} label="Median-class latency" value={`${k.avg_latency_ms} ms`} hint={`p95 ${k.p95_latency_ms} ms`} tone="violet" />
        <Stat icon={ShieldAlert} label="Access violations caught" value={k.acl_violations} hint="Should always be 0" tone={k.acl_violations ? 'red' : 'teal'} />
      </div>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat icon={FileText} label="Documents" value={totalDocs} hint={docsByStatus.map(([s, n]) => `${n} ${s}`).join(' · ') || 'None yet'} tone="amber" />
        <Stat icon={Layers} label="Indexed passages" value={k.indexed_passages.toLocaleString()} tone="teal" />
        <Stat icon={Users} label="Active users" value={usersByRole.reduce((n, r) => n + r.count, 0)} tone="blue" />
        <Stat icon={ThumbsUp} label="Feedback" value={`${k.feedback_up} 👍 / ${k.feedback_down} 👎`} tone="green" />
      </div>
      <div className="grid g-2-1" style={{ marginBottom: 16 }}>
        <Card title="Questions per day" action={<div className="legend"><span><i style={{ background: '#14b8a6' }} />Answered</span><span><i style={{ background: '#f4b740' }} />Insufficient evidence</span></div>}>
          <div className="bars" role="img" aria-label="Questions per day">
            {d.timeseries.map((x) => (
              <div className="bar-col" key={x.day} title={`${x.day}: ${x.answered} answered, ${x.fallback} insufficient`}>
                <div className="bar-stack" style={{ height: `${((x.answered + x.fallback) / maxDay) * 100}%`, minHeight: x.answered + x.fallback ? 4 : 0 }}>
                  <div className="bar-answered" style={{ flex: x.answered }} /><div className="bar-fallback" style={{ flex: x.fallback }} />
                </div>
                <span className="bar-label">{x.day.slice(5)}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Most asked (30 days)">
          {d.top_queries.length === 0 ? <Empty title="No questions yet" /> : d.top_queries.map((t) => <div className="list-row" key={t.query}><span>{t.query}</span><b>{t.count}</b></div>)}
        </Card>
      </div>
      <div className="grid g3">
        <Card title="Documents by classification"><HBars rows={docsByClass} label={(r) => labelClass(r.key)} /></Card>
        <Card title="Users by role"><HBars rows={usersByRole} label={(r) => ROLE_LABEL[r.key]} /></Card>
        <Card title="Questions by role"><HBars rows={d.queries_by_role.map((r) => ({ key: r.role, count: r.count }))} label={(r) => ROLE_LABEL[r.key] || r.key} /></Card>
      </div>
    </>
  );
}
