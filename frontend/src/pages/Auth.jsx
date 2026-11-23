import { useState } from 'react';
import { LogOut } from 'lucide-react';
import { supabase, configured } from '../supabase';
import { Spinner } from '../components/ui';

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

export function ConfigMissing() {
  return (
    <div className="login-form-wrap" style={{ minHeight: '100vh' }}>
      <div className="login-form">
        <h2>Configuration needed</h2>
        <p>Create <code>frontend/.env</code> from <code>.env.example</code> and set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_PUBLISHABLE_KEY</code>, then restart <code>npm run dev</code>.</p>
      </div>
    </div>
  );
}

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setInfo('');
    const { error: err } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (err) setError(err.message === 'Invalid login credentials' ? 'Incorrect email or password.' : err.message);
    setBusy(false);
  };
  const reset = async () => {
    if (!email.trim()) { setError('Enter your email first, then choose “Forgot password”.'); return; }
    setError('');
    const { error: err } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: window.location.origin });
    if (err) setError(err.message); else setInfo('If that account exists, a reset link has been sent.');
  };
  return (
    <Shell>
        <form className="login-form" onSubmit={submit}>
          <h2>Sign in</h2>
          <label className="field"><span>Email</span><input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
          <label className="field"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <p className="error-text" role="alert" style={{ marginBottom: 12 }}>{error}</p>}
          {info && <p className="hint" style={{ marginBottom: 12 }}>{info}</p>}
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: 13 }} disabled={busy}>{busy ? <Spinner /> : null} Sign in</button>
          <p style={{ marginTop: 16, textAlign: 'center' }}><button type="button" className="link-btn" onClick={reset}>Forgot password?</button></p>
        </form>
    </Shell>
  );
}

/** Shown after an invite or password-reset link: the user chooses their password. */
export function SetPassword({ onDone }) {
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    if (pw.length < 10) return setError('Use at least 10 characters.');
    if (pw !== pw2) return setError('The passwords do not match.');
    setBusy(true); setError('');
    const { error: err } = await supabase.auth.updateUser({ password: pw });
    setBusy(false);
    if (err) return setError(err.message);
    window.history.replaceState(null, '', window.location.pathname);
    onDone();
  };
  return (
    <Shell>
        <form className="login-form" onSubmit={submit}>
          <h2>Set password</h2>
          <label className="field"><span>New password</span><input type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} required /><p className="hint">At least 10 characters.</p></label>
          <label className="field"><span>Confirm password</span><input type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required /></label>
          {error && <p className="error-text" role="alert" style={{ marginBottom: 12 }}>{error}</p>}
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: 13 }} disabled={busy}>{busy ? <Spinner /> : null} Save and continue</button>
        </form>
    </Shell>
  );
}

export function AccessProblem({ message, onSignOut }) {
  return (
    <div className="login-form-wrap" style={{ minHeight: '100vh' }}>
      <div className="login-form">
        <h2>Access unavailable</h2>
        <p style={{ marginBottom: 18 }}>{message}</p>
        <button className="btn" onClick={onSignOut}><LogOut size={16} /> Sign out</button>
      </div>
    </div>
  );
}
