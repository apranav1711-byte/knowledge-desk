import { supabase } from './supabase';

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export async function api(path, { method = 'GET', body, form } = {}) {
  const { data } = await supabase.auth.getSession();
  const headers = {};
  if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let res;
  try { res = await fetch(`${API}/api/v1${path}`, { method, headers, body: payload }); }
  catch { const e = new Error('Cannot reach the Knowledge Desk API. Is the backend running?'); e.status = 0; throw e; }
  if (res.status === 204) return null;
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof json?.detail === 'string' ? json.detail : res.status === 422 ? 'Please check your input and try again.' : 'Something went wrong. Please try again.';
    const e = new Error(detail); e.status = res.status; throw e;
  }
  return json;
}

export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
export const fmtDateTime = (s) => (s ? new Date(s).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—');
export const fmtBytes = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
export const CLASSIFICATIONS = ['Public', 'General_Internal', 'Management', 'HR_Confidential', 'Restricted'];
export const labelClass = (c) => (c || '').replaceAll('_', ' ');
export const ROLE_LABEL = { employee: 'Employee', manager: 'Manager', hr: 'HR specialist', admin: 'Administrator' };
