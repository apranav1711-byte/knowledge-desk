import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, Eye, FileText, Pencil, Search, Trash2, Upload } from 'lucide-react';
import { API, api, CLASSIFICATIONS, fmtBytes, fmtDate, labelClass } from '../api';
import { Card, ClassBadge, Empty, Modal, Spinner, StatusBadge } from '../components/ui';
import { DocViewer } from './Assistant';

const ACCEPT = '.pdf,.docx,.xlsx,.csv,.pptx,.html,.htm,.md,.markdown,.txt';
// Mirrors backend can_upload(): you may only classify at a level you can read yourself.
const uploadable = (me) => (me.role === 'employee' ? [] : me.can_read);

function UploadModal({ me, onClose, onDone, notify }) {
  const options = uploadable(me);
  const [file, setFile] = useState(null);
  const [classification, setClassification] = useState(options.includes('General_Internal') ? 'General_Internal' : options[0]);
  const [department, setDepartment] = useState('');
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const input = useRef(null);
  const submit = async () => {
    setBusy(true);
    try {
      const form = new FormData(); form.append('file', file); form.append('classification', classification); form.append('department', department);
      const r = await api('/documents', { method: 'POST', form });
      notify(r.duplicate ? 'This file is already in the library.' : `${file.name} uploaded. Indexing…`);
      onDone(); onClose();
    } catch (e) { notify(e.message, 'err'); setBusy(false); }
  };
  return (
    <Modal title="Add a document" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-teal" disabled={!file || busy} onClick={submit}>{busy ? <Spinner /> : <Upload size={16} />} Upload & index</button></>}>
      <div className={`dropzone ${over ? 'over' : ''}`} onClick={() => input.current.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); setFile(e.dataTransfer.files[0] || null); }}>
        <strong>{file ? file.name : 'Drop a file here or click to browse'}</strong>
        {file ? fmtBytes(file.size) : 'PDF, Word, Excel, PowerPoint, CSV, HTML, Markdown or text · up to 25 MB'}
        <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => setFile(e.target.files[0] || null)} />
      </div>
      <label className="field"><span>Who may access this document?</span>
        <select value={classification} onChange={(e) => setClassification(e.target.value)}>{options.map((c) => <option key={c} value={c}>{labelClass(c)}</option>)}</select>
        </label>
      <label className="field"><span>Department (optional)</span><input type="text" value={department} maxLength={80} onChange={(e) => setDepartment(e.target.value)} /></label>
    </Modal>
  );
}

function EditModal({ doc, me, onClose, onDone, notify }) {
  const [title, setTitle] = useState(doc.title);
  const [classification, setClassification] = useState(doc.classification);
  const [busy, setBusy] = useState(false);
  const options = me.role === 'admin' ? CLASSIFICATIONS : uploadable(me);
  const save = async () => {
    setBusy(true);
    try { await api(`/documents/${doc.id}`, { method: 'PATCH', body: { title, classification } }); notify('Document updated. Access changes apply immediately.'); onDone(); onClose(); }
    catch (e) { notify(e.message, 'err'); setBusy(false); }
  };
  return (
    <Modal title="Edit document" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || !title.trim()} onClick={save}>{busy && <Spinner />} Save changes</button></>}>
      <label className="field"><span>Title</span><input type="text" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="field"><span>Access classification</span><select value={classification} onChange={(e) => setClassification(e.target.value)}>{options.map((c) => <option key={c} value={c}>{labelClass(c)}</option>)}</select>
        </label>
    </Modal>
  );
}

export default function Documents({ me, notify }) {
  const [docs, setDocs] = useState(null);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [upload, setUpload] = useState(false);
  const [edit, setEdit] = useState(null);
  const [view, setView] = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);
  const load = useCallback(() => api('/documents').then(setDocs).catch((e) => { notify(e.message, 'err'); setDocs([]); }), [notify]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { // poll while anything is still indexing
    if (!docs?.some((d) => d.status === 'processing')) return;
    const t = setInterval(load, 3000); return () => clearInterval(t);
  }, [docs, load]);

  const shown = (docs || []).filter((d) => d.title.toLowerCase().includes(q.toLowerCase()) && (filter === 'all' || d.classification === filter));
  const download = async (d) => { try { const r = await api(`/documents/${d.id}/download`); window.open(r.url.startsWith('/') ? API + r.url : r.url, '_blank', 'noopener'); } catch (e) { notify(e.message, 'err'); } };
  const remove = async () => {
    try { await api(`/documents/${confirmDel.id}`, { method: 'DELETE' }); notify('Document deleted and removed from search.'); setConfirmDel(null); load(); }
    catch (e) { notify(e.message, 'err'); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Documents</h1></div>
        {uploadable(me).length > 0 && <button className="btn btn-teal" onClick={() => setUpload(true)}><Upload size={16} /> Add document</button>}
      </div>
      <Card>
        <div className="toolbar">
          <div className="search"><Search size={16} /><input type="text" placeholder="Search documents" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <select style={{ width: 200 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All classifications</option>{me.can_read.map((c) => <option key={c} value={c}>{labelClass(c)}</option>)}
          </select>
          <span className="muted" style={{ marginLeft: 'auto' }}>{shown.length} document{shown.length === 1 ? '' : 's'}</span>
        </div>
        {!docs ? <Spinner /> : shown.length === 0 ? <Empty icon={FileText} title="No documents found"></Empty> : (
          <div className="table-wrap"><table className="data">
            <thead><tr><th>Document</th><th>Classification</th><th>Status</th><th>Passages</th><th>Added</th><th></th></tr></thead>
            <tbody>{shown.map((d) => (
              <tr key={d.id}>
                <td><div className="cell-title">{d.title}</div><div className="cell-sub">{d.filename} · {fmtBytes(d.file_size)}{d.total_pages ? ` · ${d.total_pages} page${d.total_pages > 1 ? 's' : ''}` : ''}</div>{d.error && <div className="error-text" style={{ fontSize: 12, marginTop: 3 }}>{d.error}</div>}</td>
                <td><ClassBadge value={d.classification} /></td>
                <td><StatusBadge value={d.status} /></td>
                <td>{d.total_chunks || '—'}</td>
                <td>{fmtDate(d.created_at)}</td>
                <td><div className="row-actions">
                  {d.status === 'ready' && <><button className="icon-btn" title="View passages" aria-label="View passages" onClick={() => setView(d)}><Eye size={16} /></button>
                    <button className="icon-btn" title="Download original" aria-label="Download original" onClick={() => download(d)}><Download size={16} /></button></>}
                  {d.can_manage && <><button className="icon-btn" title="Edit" aria-label="Edit" onClick={() => setEdit(d)}><Pencil size={16} /></button>
                    <button className="icon-btn" title="Delete" aria-label="Delete" onClick={() => setConfirmDel(d)}><Trash2 size={16} /></button></>}
                </div></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
      {upload && <UploadModal me={me} notify={notify} onClose={() => setUpload(false)} onDone={load} />}
      {edit && <EditModal doc={edit} me={me} notify={notify} onClose={() => setEdit(null)} onDone={load} />}
      {view && <DocViewer source={{ document_id: view.id, title: view.title, excerpt: '' }} onClose={() => setView(null)} />}
      {confirmDel && (
        <Modal title="Delete document?" onClose={() => setConfirmDel(null)} footer={<><button className="btn" onClick={() => setConfirmDel(null)}>Cancel</button><button className="btn btn-danger" onClick={remove}><Trash2 size={15} /> Delete permanently</button></>}>
          <p><b>{confirmDel.title}</b> and all its indexed passages will be removed from search. This cannot be undone.</p>
        </Modal>
      )}
    </>
  );
}
