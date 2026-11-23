import { useState } from 'react';
import { BookOpenCheck, Fingerprint, Layers, ShieldCheck, LogOut } from 'lucide-react';
import { supabase, configured } from '../supabase';
import { Spinner } from '../components/ui';

function Hero() {
  return (
    <div className="login-hero">
      <div className="brand"><span className="brand-mark">KD</span><span><strong>Knowledge Desk</strong><small>Enterprise policy intelligence</small></span></div>
      <div>
        <h1>Answers from your documents, only for the people cleared to see them.</h1>
        <p>Ask a question in plain language and get the exact supporting passage. Access is enforced before search, so restricted content is never even considered.</p>
        <div className="feature-list">
          <div><ShieldCheck size={20} /><span><b>Permission-aware retrieval</b>Role and tenant filters run inside the database query.</span></div>
          <div><BookOpenCheck size={20} /><span><b>Evidence for every answer</b>Cited passages with page and section, never invented text.</span></div>
          <div><Layers size={20} /><span><b>Real document parsing</b>PDF, Word, Excel, PowerPoint, HTML, Markdown and more.</span></div>
          <div><Fingerprint size={20} /><span><b>Tamper-evident audit trail</b>Every query and change is hash-chained and verifiable.</span></div>
        </div>
      </div>
      <small>© Knowledge Desk</small>
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
    <div className="login">
      <Hero />
      <div className="login-form-wrap">
        <form className="login-form" onSubmit={submit}>
          <h2>Sign in</h2>
          <p>Use the work account your administrator created for you.</p>
          <label className="field"><span>Email</span><input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
          <label className="field"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <p className="error-text" role="alert" style={{ marginBottom: 12 }}>{error}</p>}
          {info && <p className="hint" style={{ marginBottom: 12 }}>{info}</p>}
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: 11 }} disabled={busy}>{busy ? <Spinner /> : null} Sign in</button>
          <p style={{ marginTop: 16, textAlign: 'center' }}><button type="button" className="link-btn" onClick={reset}>Forgot password?</button></p>
        </form>
      </div>
    </div>
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
    <div className="login">
      <Hero />
      <div className="login-form-wrap">
        <form className="login-form" onSubmit={submit}>
          <h2>Choose your password</h2>
          <p>Set a password to finish activating your account.</p>
          <label className="field"><span>New password</span><input type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} required /><p className="hint">At least 10 characters.</p></label>
          <label className="field"><span>Confirm password</span><input type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required /></label>
          {error && <p className="error-text" role="alert" style={{ marginBottom: 12 }}>{error}</p>}
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: 11 }} disabled={busy}>{busy ? <Spinner /> : null} Save and continue</button>
        </form>
      </div>
    </div>
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
