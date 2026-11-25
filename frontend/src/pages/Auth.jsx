import { useState } from 'react';
import { LogOut } from 'lucide-react';
import { api, session } from '../api';
import { Modal, Spinner } from '../components/ui';

function Shell({ children }) {
  return (
    <div className="login">
      <div className="login-card">
        <div className="brand"><strong>Knowledge Desk</strong></div>
        {children}
      </div>
    </div>
  );
}

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const r = await api('/auth/login', { method: 'POST', body: { email: email.trim(), password }, auth: false });
      session.set(r.access_token);
    } catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <Shell>
        <form className="login-form" onSubmit={submit}>
          <h2>Sign in</h2>
          <label className="field"><span>Email</span><input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
          <label className="field"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <p className="error-text" role="alert" style={{ marginBottom: 12 }}>{error}</p>}
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: 13 }} disabled={busy}>{busy ? <Spinner /> : null} Sign in</button>
        </form>
    </Shell>
  );
}

export function ChangePassword({ onClose, notify }) {
  const [cur, setCur] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    if (pw.length < 10) return setError('Use at least 10 characters.');
    if (pw !== pw2) return setError('The new passwords do not match.');
    setBusy(true); setError('');
    try { await api('/auth/password', { method: 'POST', body: { current_password: cur, new_password: pw } }); notify('Password changed.'); onClose(); }
    catch (e) { setError(e.message); setBusy(false); }
  };
  return (
    <Modal title="Change password" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || !cur || !pw} onClick={save}>{busy ? <Spinner /> : null} Save</button></>}>
      <div className="login-form">
        <label className="field"><span>Current password</span><input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} autoFocus /></label>
        <label className="field"><span>New password</span><input type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /><p className="hint">At least 10 characters.</p></label>
        <label className="field"><span>Confirm new password</span><input type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></label>
        {error && <p className="error-text" role="alert">{error}</p>}
      </div>
    </Modal>
  );
}

export function AccessProblem({ message, onSignOut, onRetry }) {
  return (
    <div className="login">
      <div className="login-card">
        <div className="brand"><strong>Knowledge Desk</strong></div>
        <p style={{ marginBottom: 18 }}>{message}</p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
          {onRetry && <button className="btn btn-primary" onClick={onRetry}>Try again</button>}
          <button className="btn" onClick={onSignOut}><LogOut size={16} /> Sign out</button>
        </div>
      </div>
    </div>
  );
}
