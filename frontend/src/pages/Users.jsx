import { useCallback, useEffect, useState } from 'react';
import { Plus, UserPlus } from 'lucide-react';
import { api, fmtDate, ROLE_LABEL } from '../api';
import { Badge, Card, Empty, Modal, RoleBadge, Spinner } from '../components/ui';

const ROLES = ['employee', 'manager', 'hr', 'admin'];
const ROLE_HELP = {
  employee: 'Public and General Internal documents.', manager: 'Adds Management documents.',
  hr: 'Adds HR Confidential documents (not Management).', admin: 'Everything, plus users, audit and analytics.',
};

function AddUser({ onClose, onDone, notify }) {
  const [f, setF] = useState({ email: '', full_name: '', department: '', role: 'employee', password: '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const body = { ...f };
      const r = await api('/admin/users', { method: 'POST', body });
      notify(`${f.email} created. Share the password securely.`); onDone(); onClose();
    } catch (e) { notify(e.message, 'err'); setBusy(false); }
  };
  const valid = f.email.includes('@') && f.full_name.trim() && f.password.length >= 10;
  return (
    <Modal title="Add a user" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-teal" disabled={!valid || busy} onClick={save}>{busy ? <Spinner /> : <UserPlus size={16} />} Create user</button></>}>
      <label className="field"><span>Full name</span><input type="text" value={f.full_name} onChange={set('full_name')} /></label>
      <label className="field"><span>Work email</span><input type="email" value={f.email} onChange={set('email')} /></label>
      <label className="field"><span>Department</span><input type="text" value={f.department} onChange={set('department')} /></label>
      <label className="field"><span>Role</span><select value={f.role} onChange={set('role')}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select><p className="hint">{ROLE_HELP[f.role]}</p></label>
      <label className="field"><span>Temporary password</span><input type="password" autoComplete="new-password" value={f.password} onChange={set('password')} />
        <p className="hint">At least 10 characters. They can change it from the account menu.</p></label>
    </Modal>
  );
}

export default function Users({ me, notify }) {
  const [users, setUsers] = useState(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => api('/admin/users').then(setUsers).catch((e) => { notify(e.message, 'err'); setUsers([]); }), [notify]);
  useEffect(() => { load(); }, [load]);
  const patch = async (u, body, msg) => {
    try { await api(`/admin/users/${u.id}`, { method: 'PATCH', body }); notify(msg); load(); } catch (e) { notify(e.message, 'err'); }
  };
  return (
    <>
      <div className="page-head"><div><h1>Users</h1></div>
        <button className="btn btn-teal" onClick={() => setAdding(true)}><Plus size={16} /> Add user</button></div>
      <Card>
        {!users ? <Spinner /> : users.length === 0 ? <Empty title="No users yet" /> : (
          <div className="table-wrap"><table className="data">
            <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Added</th><th></th></tr></thead>
            <tbody>{users.map((u) => (
              <tr key={u.id}>
                <td><div className="cell-title">{u.full_name || '—'} {u.id === me.id && <Badge tone="blue">You</Badge>}</div><div className="cell-sub">{u.email}{u.department ? ` · ${u.department}` : ''}</div></td>
                <td><select style={{ width: 170 }} value={u.role} aria-label={`Role for ${u.email}`}
                  onChange={(e) => patch(u, { role: e.target.value }, `${u.email} is now ${ROLE_LABEL[e.target.value]}.`)}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></td>
                <td>{u.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="red">Deactivated</Badge>}
                  <button className="btn btn-sm" style={{ marginLeft: 10 }} onClick={() => patch(u, { is_active: !u.is_active }, u.is_active ? `${u.email} deactivated.` : `${u.email} reactivated.`)}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button></td>
                <td>{fmtDate(u.created_at)}</td>
                <td>{u.id !== me.id && <button className="btn btn-sm" onClick={() => {
                  const pw = window.prompt(`New temporary password for ${u.email} (at least 10 characters):`);
                  if (pw === null) return;
                  if (pw.length < 10) { notify('Use at least 10 characters.', 'err'); return; }
                  patch(u, { password: pw }, `Password reset for ${u.email}. Share it securely.`);
                }}>Reset password</button>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
      {adding && <AddUser onClose={() => setAdding(false)} onDone={load} notify={notify} />}
    </>
  );
}
