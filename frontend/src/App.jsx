import { useCallback, useEffect, useState } from 'react';
import { BarChart3, FileText, LayoutDashboard, LogOut, MessageSquareText, ShieldCheck, Users as UsersIcon } from 'lucide-react';
import { api, session } from './api';
import { Spinner, Toast, RoleBadge } from './components/ui';
import { AccessProblem, ChangePassword, Login } from './pages/Auth';
import Overview from './pages/Overview';
import Assistant from './pages/Assistant';
import Documents from './pages/Documents';
import Users from './pages/Users';
import Analytics from './pages/Analytics';
import Audit from './pages/Audit';

const initials = (n) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');

export default function App() {
  const [token, setToken] = useState(() => session.get());
  const [me, setMe] = useState(null);
  const [problem, setProblem] = useState('');
  const [page, setPage] = useState('overview');
  const [pageArg, setPageArg] = useState(null);
  const [toast, setToast] = useState(null);
  const [changingPw, setChangingPw] = useState(false);
  const notify = useCallback((text, tone = 'ok') => setToast({ text, tone, id: Date.now() }), []);

  useEffect(() => {
    const sync = () => setToken(session.get());
    window.addEventListener('kd-session', sync);
    window.addEventListener('storage', sync); // sign-in/out in another tab
    return () => { window.removeEventListener('kd-session', sync); window.removeEventListener('storage', sync); };
  }, []);

  const loadMe = useCallback(() => {
    setProblem(''); setMe(null);
    api('/me').then(setMe).catch((e) => { if (e.status !== 401) setProblem(e.message); });
  }, []);
  useEffect(() => { if (token) loadMe(); else { setMe(null); setProblem(''); setPage('overview'); } }, [token, loadMe]);

  const signOut = () => session.clear();
  const go = (p, arg = null) => { setPage(p); setPageArg(arg); window.scrollTo(0, 0); };

  if (!token) return <Login />;
  if (problem) return <AccessProblem message={problem} onSignOut={signOut} onRetry={loadMe} />;
  if (!me) return <div className="login-form-wrap" style={{ minHeight: '100vh' }}><Spinner size={24} /></div>;

  const nav = [
    ['overview', 'Overview', LayoutDashboard], ['assistant', 'Assistant', MessageSquareText], ['documents', 'Documents', FileText],
    ...(me.permissions.manage_users ? [['users', 'Users', UsersIcon]] : []),
    ...(me.permissions.view_analytics ? [['analytics', 'Analytics', BarChart3]] : []),
    ...(me.permissions.view_audit ? [['audit', 'Audit', ShieldCheck]] : []),
  ];
  const props = { me, go, notify, arg: pageArg };

  return (
    <div className="shell">
      <header className="topnav">
        <div className="brand"><strong>Knowledge Desk</strong></div>
        <nav className="nav" aria-label="Main">
          {nav.map(([id, label]) => <button key={id} className={page === id ? 'active' : ''} onClick={() => go(id)}>{label}</button>)}
        </nav>
        <div className="user-chip">
          <div className="who"><div>{me.full_name || me.email}</div></div>
          <RoleBadge value={me.role} />
          <button className="avatar" style={{ border: 0 }} title="Change password" aria-label="Change password" onClick={() => setChangingPw(true)}>{initials(me.full_name || me.email)}</button>
          <button className="icon-btn" onClick={signOut} title="Sign out" aria-label="Sign out"><LogOut size={18} /></button>
        </div>
      </header>
      <div className="main">
        <main className="content">
          {page === 'overview' && <Overview {...props} />}
          {page === 'assistant' && <Assistant {...props} />}
          {page === 'documents' && <Documents {...props} />}
          {page === 'users' && <Users {...props} />}
          {page === 'analytics' && <Analytics {...props} />}
          {page === 'audit' && <Audit {...props} />}
        </main>
      </div>
      {changingPw && <ChangePassword onClose={() => setChangingPw(false)} notify={notify} />}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}
