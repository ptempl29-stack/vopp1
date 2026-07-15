import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { Private } from "../context/PrivacyContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { useSelection, bulkDelete } from "../lib/bulk";
import {
  Folder, FolderOpen, FolderPlus, ChevronLeft, Download, FileText, Upload,
  Pencil, Trash2, Search, Plus, MoveRight, ClipboardList, Users,
} from "lucide-react";
import { toast } from "sonner";

const sourceIcon = { form: ClipboardList, upload: FileText };
const sourceTone = { form: "green", upload: "tan" };

export default function PatientFolders() {
  const { t } = useLang();
  const [patients, setPatients] = useState([]);
  const [query, setQuery] = useState("");
  const [openFolder, setOpenFolder] = useState(null); // {patient_id, patient_name, subfolders, items}
  const [activeSub, setActiveSub] = useState("all"); // "all" | "root" | subfolder id
  const [attachOptions, setAttachOptions] = useState([]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  // modals
  const [subModal, setSubModal] = useState(null); // {id?, name}
  const [editModal, setEditModal] = useState(null); // item
  const [moveModal, setMoveModal] = useState(null); // item

  const sel = useSelection();

  const loadPatients = useCallback(async () => {
    try { setPatients((await api.get("/folders/patients")).data); } catch (e) { toast.error(apiErr(e)); }
  }, []);

  useEffect(() => {
    loadPatients();
    api.get("/folders/options/forms").then((r) => setAttachOptions(r.data)).catch(() => {});
  }, [loadPatients]);

  const openPatient = async (pid) => {
    try {
      const r = await api.get(`/folders/${pid}`);
      setOpenFolder(r.data); setActiveSub("all"); sel.clear();
    } catch (e) { toast.error(apiErr(e)); }
  };
  const refresh = async () => { if (openFolder) { const r = await api.get(`/folders/${openFolder.patient_id}`); setOpenFolder(r.data); } };

  const filteredPatients = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? patients.filter((p) => p.name.toLowerCase().includes(q)) : patients;
  }, [patients, query]);

  // ---------- Actions ----------
  const saveSubfolder = async (e) => {
    e.preventDefault();
    try {
      if (subModal.id) await api.put(`/folders/subfolders/${subModal.id}`, { name: subModal.name });
      else await api.post(`/folders/${openFolder.patient_id}/subfolders`, { name: subModal.name });
      toast.success(t("subfolderCreated")); setSubModal(null); refresh();
    } catch (err) { toast.error(apiErr(err)); }
  };
  const deleteSubfolder = async (sid) => {
    try {
      await api.delete(`/folders/subfolders/${sid}`);
      toast.success(t("delete") + " ✓");
      if (activeSub === sid) setActiveSub("all");
      refresh();
    } catch (e) { toast.error(apiErr(e)); }
  };

  const onUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("subfolder_id", activeSub !== "all" && activeSub !== "root" ? activeSub : "");
    setBusy(true);
    try {
      await api.post(`/folders/${openFolder.patient_id}/upload`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(t("uploadToFolder") + " ✓"); refresh();
    } catch (err) { toast.error(apiErr(err)); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const [pickForm, setPickForm] = useState("");
  const attachForm = async () => {
    if (!pickForm) return;
    try {
      await api.post(`/folders/${openFolder.patient_id}/attach-form`, {
        form_id: pickForm,
        subfolder_id: activeSub !== "all" && activeSub !== "root" ? activeSub : null,
      });
      toast.success(t("attachToFolder") + " ✓"); setPickForm(""); refresh();
    } catch (e) { toast.error(apiErr(e)); }
  };

  const saveEdit = async (e) => {
    e.preventDefault();
    try {
      await api.put(`/folders/items/${editModal.id}`, { label: editModal.label, description: editModal.description || "" });
      toast.success(t("itemSaved")); setEditModal(null); refresh();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const doMove = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/folders/items/${moveModal.id}/move`, {
        patient_id: moveModal.target_patient, subfolder_id: moveModal.target_sub || null,
      });
      toast.success(t("movedOk")); setMoveModal(null); refresh(); loadPatients();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const deleteItem = async (id) => {
    try { await api.delete(`/folders/items/${id}`); toast.success(t("delete") + " ✓"); refresh(); loadPatients(); }
    catch (e) { toast.error(apiErr(e)); }
  };

  const authedDownload = async (id, fallbackName) => {
    try {
      const r = await api.get(`/folders/items/${id}/download`, { responseType: "blob" });
      const cd = r.headers["content-disposition"] || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const href = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = href; a.download = m ? m[1] : fallbackName; a.click();
      URL.revokeObjectURL(href);
    } catch (e) { toast.error(apiErr(e)); }
  };

  // ---------- Detail (open folder) ----------
  if (openFolder) {
    const subs = openFolder.subfolders || [];
    const items = openFolder.items || [];
    const visible = items.filter((it) =>
      activeSub === "all" ? true : activeSub === "root" ? !it.subfolder_id : it.subfolder_id === activeSub);
    const visibleIds = visible.map((v) => v.id);
    const subName = (id) => subs.find((s) => s.id === id)?.name || t("unfiled");

    return (
      <div data-testid="folder-detail">
        <PageHeader title={<Private value={openFolder.patient_name} />} subtitle={`${items.length} ${t("documents")}`}
          action={
            <div className="flex flex-wrap gap-2">
              <Btn variant="outline" onClick={() => { setOpenFolder(null); loadPatients(); }} data-testid="folder-back"><ChevronLeft className="w-4 h-4" />{t("backToFolders")}</Btn>
              <Btn variant="outline" onClick={() => setSubModal({ name: "" })} data-testid="new-subfolder-btn"><FolderPlus className="w-4 h-4" />{t("newSubfolder")}</Btn>
            </div>} />

        {/* Subfolder chips */}
        <div className="flex flex-wrap gap-2 mb-5">
          {[{ id: "all", name: t("allItems") }, { id: "root", name: t("unfiled") }, ...subs].map((s) => {
            const active = activeSub === s.id;
            const isReal = s.id !== "all" && s.id !== "root";
            return (
              <div key={s.id} className={`group inline-flex items-center rounded-full border transition-colors duration-200 ${active ? "bg-moneygreen-600 border-moneygreen-600 text-white" : "bg-white border-border text-moneygreen-700 hover:bg-moneygreen-50"}`}>
                <button onClick={() => { setActiveSub(s.id); sel.clear(); }} data-testid={`sub-chip-${s.id}`}
                  className="inline-flex items-center gap-1.5 pl-3 pr-2 py-1.5 text-sm font-semibold">
                  {isReal ? (active ? <FolderOpen className="w-4 h-4" /> : <Folder className="w-4 h-4" />) : null}
                  {s.name}
                </button>
                {isReal && (
                  <span className="flex items-center pr-1.5 gap-0.5">
                    <button onClick={() => setSubModal({ id: s.id, name: s.name })} data-testid={`rename-sub-${s.id}`}
                      title={t("renameSubfolder")} className={`p-1 rounded ${active ? "hover:bg-moneygreen-700" : "hover:bg-moneygreen-100"}`}><Pencil className="w-3.5 h-3.5" /></button>
                    <button onClick={() => { if (window.confirm(t("confirmDeleteFolder"))) deleteSubfolder(s.id); }} data-testid={`delete-sub-${s.id}`}
                      title={t("renameSubfolder")} className={`p-1 rounded ${active ? "hover:bg-moneygreen-700" : "hover:bg-red-100 text-destructive"}`}><Trash2 className="w-3.5 h-3.5" /></button>
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Toolbar */}
        <Card className="p-4 mb-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("uploadToFolder")}</label>
              <div className="mt-1.5">
                <input ref={fileRef} type="file" onChange={onUpload} data-testid="folder-upload-input"
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.txt,.xls,.xlsx" disabled={busy}
                  className="block w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer disabled:opacity-60" />
              </div>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("attachToFolder")}</label>
              <div className="flex gap-2 mt-1.5">
                <select value={pickForm} onChange={(e) => setPickForm(e.target.value)} className={inputCls} data-testid="folder-pick-form">
                  <option value="">{t("selectForm")}</option>
                  {attachOptions.map((f) => <option key={f.id} value={f.id}>{f.title} · {f.patient_name}</option>)}
                </select>
                <Btn variant="outline" onClick={attachForm} disabled={!pickForm} data-testid="folder-attach-form" className="!px-3"><Plus className="w-4 h-4" /></Btn>
              </div>
            </div>
          </div>
        </Card>

        {/* Selection bar */}
        {visible.length > 0 && (
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-stone-600 cursor-pointer" data-testid="folder-select-all">
              <input type="checkbox" checked={sel.count > 0 && sel.count >= visibleIds.length}
                onChange={() => sel.toggleAll(visibleIds)} className="w-4 h-4 accent-moneygreen-600" />
              {sel.count >= visibleIds.length && visibleIds.length > 0 ? t("deselectAll") : t("selectAll")}
            </label>
            {sel.count > 0 && (
              <Btn variant="danger" data-testid="folder-bulk-delete"
                onClick={async () => { await bulkDelete("/folders/items/bulk-delete", [...sel.selected], t); sel.clear(); refresh(); loadPatients(); }}>
                <Trash2 className="w-4 h-4" />{t("deleteSelected")} ({sel.count})
              </Btn>
            )}
          </div>
        )}

        {/* Items table */}
        <Card className="overflow-hidden">
          {visible.length === 0 ? <Empty text={t("noDocsInFolder")} /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="px-4 py-3 w-10"></th>
                    <th className="px-4 py-3">{t("itemLabel")}</th>
                    <th className="px-4 py-3 hidden md:table-cell">{t("itemSource")}</th>
                    <th className="px-4 py-3 hidden lg:table-cell">{t("newSubfolder")}</th>
                    <th className="px-4 py-3 hidden md:table-cell">{t("filename")}</th>
                    <th className="px-4 py-3 text-right">{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((it, i) => {
                    const Icon = sourceIcon[it.source] || FileText;
                    return (
                      <motion.tr key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                        data-testid={`folder-item-${it.id}`}
                        className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                        <td className="px-4 py-3">
                          <input type="checkbox" checked={sel.has(it.id)} onChange={() => sel.toggle(it.id)}
                            data-testid={`folder-item-check-${it.id}`} className="w-4 h-4 accent-moneygreen-600" />
                        </td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-2 font-semibold text-moneygreen-800"><Icon className="w-4 h-4 text-stone-400" />{it.label || it.filename}</span>
                          {it.description && <p className="text-xs text-stone-500 mt-0.5 line-clamp-1">{it.description}</p>}
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell"><Badge tone={sourceTone[it.source] || "gray"}>{t(`src_${it.source}`)}</Badge></td>
                        <td className="px-4 py-3 hidden lg:table-cell text-stone-500 text-xs">{it.subfolder_id ? subName(it.subfolder_id) : t("unfiled")}</td>
                        <td className="px-4 py-3 hidden md:table-cell text-stone-500 text-xs">{it.filename}</td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-1">
                            <Btn variant="ghost" onClick={() => authedDownload(it.id, it.filename)} data-testid={`folder-download-${it.id}`} className="!px-2" title={t("download")}><Download className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => setEditModal({ id: it.id, label: it.label || it.filename, description: it.description || "" })} data-testid={`folder-edit-${it.id}`} className="!px-2" title={t("editItem")}><Pencil className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => setMoveModal({ id: it.id, target_patient: openFolder.patient_id, target_sub: it.subfolder_id || "", subs })} data-testid={`folder-move-${it.id}`} className="!px-2" title={t("moveItem")}><MoveRight className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => deleteItem(it.id)} data-testid={`folder-delete-${it.id}`} className="!px-2 !text-destructive" title={t("delete")}><Trash2 className="w-4 h-4" /></Btn>
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <SubfolderModal state={subModal} onClose={() => setSubModal(null)} onSave={saveSubfolder} setState={setSubModal} t={t} />
        <EditItemModal state={editModal} onClose={() => setEditModal(null)} onSave={saveEdit} setState={setEditModal} t={t} />
        <MoveModal state={moveModal} onClose={() => setMoveModal(null)} onSave={doMove} setState={setMoveModal} t={t} patients={patients} />
      </div>
    );
  }

  // ---------- List (all patient folders) ----------
  return (
    <div data-testid="folders-page">
      <PageHeader title={t("patientFolders")} subtitle={t("foldersSubtitle")}
        action={
          <div className="relative">
            <Search className="w-4 h-4 text-stone-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("searchPatients")}
              data-testid="folder-search" className={`${inputCls} pl-9 w-64`} />
          </div>} />

      {filteredPatients.length === 0 ? (
        <Card><Empty text={t("noFoldersYet")} /></Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredPatients.map((p, i) => (
            <motion.div key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
              <Card className="p-5 cursor-pointer hover:shadow-md hover:border-moneygreen-300 transition-all duration-200"
                data-testid={`folder-card-${p.id}`} onClick={() => openPatient(p.id)}>
                <div className="flex items-start gap-3">
                  <div className="w-11 h-11 rounded-md bg-tan-200 flex items-center justify-center shrink-0">
                    <Folder className="w-6 h-6 text-moneygreen-700" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-heading font-bold text-moneygreen-800 truncate"><Private value={p.name} /></p>
                    <p className="text-xs text-stone-500 mt-0.5"><Private value={p.dob || "—"} /></p>
                  </div>
                </div>
                <div className="flex items-center gap-4 mt-4 text-xs text-stone-500">
                  <span className="inline-flex items-center gap-1"><FileText className="w-3.5 h-3.5" />{p.item_count} {t("documents")}</span>
                  <span className="inline-flex items-center gap-1"><Folder className="w-3.5 h-3.5" />{p.subfolder_count} {t("subfoldersLabel")}</span>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

function SubfolderModal({ state, onClose, onSave, setState, t }) {
  return (
    <Modal open={!!state} onClose={onClose} title={state?.id ? t("renameSubfolder") : t("newSubfolder")}>
      {state && (
        <form onSubmit={onSave} className="space-y-4">
          <Field label={t("subfolderName")}>
            <input required autoFocus value={state.name} onChange={(e) => setState({ ...state, name: e.target.value })} className={inputCls} data-testid="subfolder-name-input" />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={onClose}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-subfolder-btn">{t("save")}</Btn>
          </div>
        </form>
      )}
    </Modal>
  );
}

function EditItemModal({ state, onClose, onSave, setState, t }) {
  return (
    <Modal open={!!state} onClose={onClose} title={t("editItem")}>
      {state && (
        <form onSubmit={onSave} className="space-y-4">
          <Field label={t("itemLabel")}>
            <input required value={state.label} onChange={(e) => setState({ ...state, label: e.target.value })} className={inputCls} data-testid="item-label-input" />
          </Field>
          <Field label={t("itemDescription")}>
            <textarea rows={3} value={state.description} onChange={(e) => setState({ ...state, description: e.target.value })} className={inputCls} data-testid="item-desc-input" />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={onClose}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-item-btn">{t("save")}</Btn>
          </div>
        </form>
      )}
    </Modal>
  );
}

function MoveModal({ state, onClose, onSave, setState, t, patients }) {
  const [targetSubs, setTargetSubs] = useState([]);
  useEffect(() => {
    if (!state) return;
    // default: current patient's own subfolders already known
    setTargetSubs(state.subs || []);
    if (state.target_patient) {
      api.get(`/folders/${state.target_patient}`).then((r) => setTargetSubs(r.data.subfolders || [])).catch(() => {});
    }
  }, [state?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const changePatient = async (pid) => {
    setState({ ...state, target_patient: pid, target_sub: "" });
    try { setTargetSubs((await api.get(`/folders/${pid}`)).data.subfolders || []); } catch { setTargetSubs([]); }
  };

  return (
    <Modal open={!!state} onClose={onClose} title={t("moveTo")}>
      {state && (
        <form onSubmit={onSave} className="space-y-4">
          <Field label={t("targetPatient")}>
            <select value={state.target_patient} onChange={(e) => changePatient(e.target.value)} className={inputCls} data-testid="move-patient-select">
              {patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label={t("targetFolder")}>
            <select value={state.target_sub} onChange={(e) => setState({ ...state, target_sub: e.target.value })} className={inputCls} data-testid="move-subfolder-select">
              <option value="">{t("unfiled")}</option>
              {targetSubs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={onClose}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="confirm-move-btn"><MoveRight className="w-4 h-4" />{t("moveItem")}</Btn>
          </div>
        </form>
      )}
    </Modal>
  );
}
