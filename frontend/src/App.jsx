import { useCallback, useEffect, useState } from 'react';
import { BarChart3, FileText, LayoutDashboard, LogOut, MessageSquareText, ShieldCheck, Users as UsersIcon, Lock } from 'lucide-react';
import { api, ROLE_LABEL } from './api';
import { supabase, configured } from './supabase';
import { Spinner, Toast, RoleBadge } from './components/ui';
import { AccessProblem, ConfigMissing, Login, SetPassword } from './pages/Auth';
import Overview from './pages/Overview';
import Assistant from './pages/Assistant';
import Documents from './pages/Documents';
import Users from './pages/Users';
import Analytics from './pages/Analytics';
import Audit from './pages/Audit';

const initials = (n) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');

export default function App() {
  if (!configured) return <ConfigMissing />;
  return <Authenticated />;
}

function Authenticated() {
  const [session, setSession] = useState(undefined); // undefined = still loading
  const [settingPassword, setSettingPassword] = useState(() => /type=(invite|recovery)/.test(window.location.hash));
  const [me, setMe] = useState(null);
  const [problem, setProblem] = useState('');
  const [page, setPage] = useState('overview');
  const [pageArg, setPageArg] = useState(null);
  const [toast, setToast] = useState(null);
  const notify = useCallback((text, tone = 'ok') => setToast({ text, tone, id: Date.now() }), []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((event, s) => {
      setSession(s);
      if (event === 'PASSWORD_RECOVERY') setSettingPassword(true);
      if (event === 'SIGNED_OUT') { setMe(null); setProblem(''); setPage('overview'); }
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const userId = session?.user?.id;
  useEffect(() => {
    if (!userId || settingPassword) return;
    setProblem(''); setMe(null);
    api('/me').then(setMe).catch((e) => setProblem(e.status === 403 ? e.message : e.status === 0 ? e.message : 'Could not load your profile. ' + e.message));
  }, [userId, settingPassword]);

  const signOut = () => supabase.auth.signOut();
  const go = (p, arg = null) => { setPage(p); setPageArg(arg); window.scrollTo(0, 0); };

  if (session === undefined) return <div className="login-form-wrap" style={{ minHeight: '100vh' }}><Spinner size={24} /></div>;
  if (settingPassword && session) return <SetPassword onDone={() => setSettingPassword(false)} />;
  if (!session) return <Login />;
  if (problem) return <AccessProblem message={problem} onSignOut={signOut} />;
  if (!me) return <div className="login-form-wrap" style={{ minHeight: '100vh' }}><Spinner size={24} /></div>;

  const nav = [
    ['overview', 'Overview', LayoutDashboard], ['assistant', 'Ask the assistant', MessageSquareText], ['documents', 'Documents', FileText],
    ...(me.permissions.manage_users ? [['users', 'Users & roles', UsersIcon]] : []),
    ...(me.permissions.view_analytics ? [['analytics', 'Analytics', BarChart3]] : []),
    ...(me.permissions.view_audit ? [['audit', 'Audit & security', ShieldCheck]] : []),
  ];
  const title = nav.find((n) => n[0] === page)?.[1];
  const props = { me, go, notify, arg: pageArg };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">KD</span><span><strong>Knowledge Desk</strong><small>Policy intelligence</small></span></div>
        <nav className="nav" aria-label="Main">
          <span className="nav-label">Workspace</span>
          {nav.map(([id, label, Icon]) => (
            <button key={id} className={page === id ? 'active' : ''} onClick={() => go(id)}><Icon size={17} />{label}</button>
          ))}
        </nav>
        <div className="sidebar-foot"><b><Lock size={14} /> Access is enforced first</b>You only see and search documents cleared for the <b style={{ display: 'inline' }}>{ROLE_LABEL[me.role]}</b> role.</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumbs">Knowledge Desk / <strong>{title}</strong></div>
          <div className="user-chip">
            <div className="who"><div>{me.full_name || me.email}</div><small>{me.department || me.email}</small></div>
            <RoleBadge value={me.role} />
            <span className="avatar" aria-hidden>{initials(me.full_name || me.email)}</span>
            <button className="icon-btn" onClick={signOut} title="Sign out" aria-label="Sign out"><LogOut size={18} /></button>
          </div>
        </header>
        <main className="content">
          {page === 'overview' && <Overview {...props} />}
          {page === 'assistant' && <Assistant {...props} />}
          {page === 'documents' && <Documents {...props} />}
          {page === 'users' && <Users {...props} />}
          {page === 'analytics' && <Analytics {...props} />}
          {page === 'audit' && <Audit {...props} />}
        </main>
      </div>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}
