import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import {
  FolderArchive, Plus, Pencil, Trash2, ChevronLeft, Download, FileText,
  ReceiptText, Upload, FilePlus, CalendarClock, Eye, FolderInput, Send, ArrowUp, ArrowDown,
} from "lucide-react";
import { toast } from "sonner";

const sourceIcon = { form: FileText, invoice: ReceiptText, upload: Upload, note: FileText };
const sourceTone = { form: "green", invoice: "amber", upload: "tan", note: "green" };
const blankForm = { name: "", patient_id: "", claim_number: "", status: "draft", notes: "" };

export default function Claims() {
  const { t } = useLang();
  const [packets, setPackets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankForm);
  const [patients, setPatients] = useState([]);
  const [forms, setForms] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [pickForm, setPickForm] = useState("");
  const [pickInvoice, setPickInvoice] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const [fromDateOpen, setFromDateOpen] = useState(false);
  const [fromDate, setFromDate] = useState({ patient_id: "", date: "" });
  const [building, setBuilding] = useState(false);
  const [preview, setPreview] = useState(null);
  const [renameItem, setRenameItem] = useState(null);
  const [sendOpen, setSendOpen] = useState(false);
  const [sendTo, setSendTo] = useState("");
  const [sendBusy, setSendBusy] = useState(false);

  const load = useCallback(async () => {
    try { setPackets((await api.get("/claims")).data); } catch (e) { toast.error(apiErr(e)); }
  }, []);

  useEffect(() => {
    load();
    api.get("/claims/options/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/claims/options/forms").then((r) => setForms(r.data)).catch(() => {});
    api.get("/claims/options/invoices").then((r) => setInvoices(r.data)).catch(() => {});
  }, [load]);

  const refreshSelected = async (cid) => {
    try { setSelected((await api.get(`/claims/${cid}`)).data); } catch (e) { toast.error(apiErr(e)); }
  };

  const openNew = () => { setEditing(null); setForm(blankForm); setModalOpen(true); };
  const openEdit = (p) => {
    setEditing(p);
    setForm({ name: p.name || "", patient_id: p.patient_id || "", claim_number: p.claim_number || "",
      status: p.status || "draft", notes: p.notes || "" });
    setModalOpen(true);
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const fmtDate = (d) => {
    if (!d) return "";
    const m = String(d).slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return m ? `${m[2]}/${m[3]}/${m[1]}` : d;
  };
  const buildName = (pid, dateStr) => {
    const p = patients.find((x) => x.id === pid);
    return [p ? p.name : "", fmtDate(dateStr), "FMP Claim"].filter(Boolean).join(" ");
  };
  const setClaimPatient = (e) => {
    const pid = e.target.value;
    setForm((f) => ({ ...f, patient_id: pid, name: buildName(pid, f.claim_number) }));
  };
  const setClaimDate = (e) => {
    const v = e.target.value;
    setForm((f) => ({ ...f, claim_number: v, name: buildName(f.patient_id, v) }));
  };

  const save = async (e) => {
    e.preventDefault();
    const payload = { ...form, patient_id: form.patient_id || null, claim_number: form.claim_number || null };
    try {
      if (editing) {
        const r = await api.put(`/claims/${editing.id}`, payload);
        if (selected?.id === editing.id) setSelected(r.data);
      } else {
        await api.post("/claims", payload);
      }
      toast.success(t("packetSaved"));
      setModalOpen(false); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const remove = async (id) => {
    if (!window.confirm(t("confirmDeletePacket"))) return;
    try { await api.delete(`/claims/${id}`); toast.success(t("delete") + " ✓"); load(); }
    catch (e) { toast.error(apiErr(e)); }
  };

  const buildFromDate = async (e) => {
    e.preventDefault();
    if (!fromDate.patient_id || !fromDate.date) return;
    setBuilding(true);
    try {
      const r = await api.post("/claims/from-date", fromDate);
      toast.success(t("packetSaved"));
      setFromDateOpen(false);
      setFromDate({ patient_id: "", date: "" });
      load();
      setSelected(r.data);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setBuilding(false); }
  };

  const attachForm = async () => {
    if (!pickForm) return;
    try { setSelected((await api.post(`/claims/${selected.id}/attach-form`, { form_id: pickForm })).data); setPickForm(""); }
    catch (e) { toast.error(apiErr(e)); }
  };
  const attachInvoice = async () => {
    if (!pickInvoice) return;
    try { setSelected((await api.post(`/claims/${selected.id}/attach-invoice`, { invoice_id: pickInvoice })).data); setPickInvoice(""); }
    catch (e) { toast.error(apiErr(e)); }
  };
  const onUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      setSelected((await api.post(`/claims/${selected.id}/upload`, fd, { headers: { "Content-Type": "multipart/form-data" } })).data);
      toast.success(t("uploadDocument") + " ✓");
    } catch (err) { toast.error(apiErr(err)); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const removeItem = async (itemId) => {
    try { setSelected((await api.delete(`/claims/${selected.id}/items/${itemId}`)).data); }
    catch (e) { toast.error(apiErr(e)); }
  };

  const authedDownload = async (url, fallbackName) => {
    try {
      const r = await api.get(url, { responseType: "blob" });
      const cd = r.headers["content-disposition"] || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const href = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = href; a.download = m ? m[1] : fallbackName; a.click();
      URL.revokeObjectURL(href);
    } catch (e) { toast.error(apiErr(e)); }
  };

  const previewItem = async (it) => {
    try {
      const r = await api.get(`/claims/${selected.id}/items/${it.id}/download`, { responseType: "blob" });
      const fn = (it.filename || "").toLowerCase();
      const isPdf = fn.endsWith(".pdf");
      const isImg = /\.(png|jpe?g|webp)$/.test(fn);
      const blob = new Blob([r.data], { type: isPdf ? "application/pdf" : (isImg ? "image/*" : "application/octet-stream") });
      const url = URL.createObjectURL(blob);
      if (isPdf || isImg) setPreview({ label: it.filename, kind: isPdf ? "pdf" : "img", url });
      else { authedDownload(`/claims/${selected.id}/items/${it.id}/download`, it.filename); URL.revokeObjectURL(url); }
    } catch (e) { toast.error(apiErr(e)); }
  };
  const closePreview = () => { if (preview?.url) URL.revokeObjectURL(preview.url); setPreview(null); };

  const saveRename = async (e) => {
    e.preventDefault();
    try {
      const r = await api.put(`/claims/${selected.id}/items/${renameItem.id}`, { filename: renameItem.filename });
      setSelected(r.data); setRenameItem(null); toast.success(t("saved"));
    } catch (err) { toast.error(apiErr(err)); }
  };

  const moveItemToFolder = async (it) => {
    try {
      const r = await api.post(`/claims/${selected.id}/items/${it.id}/to-folder`);
      toast.success(`${t("savedToFolder")} · ${r.data.subfolder}`);
    } catch (e) { toast.error(apiErr(e)); }
  };

  const reorderItem = async (idx, dir) => {
    const items = [...(selected.items || [])];
    const j = idx + dir;
    if (j < 0 || j >= items.length) return;
    [items[idx], items[j]] = [items[j], items[idx]];
    setSelected({ ...selected, items });
    try { await api.put(`/claims/${selected.id}/items-order`, { ids: items.map((x) => x.id) }); }
    catch (e) { toast.error(apiErr(e)); refreshSelected(selected.id); }
  };

  const sendPacket = async (e) => {
    e.preventDefault();
    setSendBusy(true);
    try {
      await api.post(`/claims/${selected.id}/send-email`, { to: sendTo });
      toast.success(`${t("sent")} ${sendTo}`);
      setSendOpen(false); refreshSelected(selected.id);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSendBusy(false); }
  };

  const statusTone = (s) => (s === "complete" ? "green" : s === "submitted" ? "tan" : "amber");

  // ---------- Detail view ----------
  if (selected) {
    const items = selected.items || [];
    return (
      <div data-testid="claim-detail">
        <PageHeader title={selected.name}
          subtitle={`${selected.claim_number ? fmtDate(selected.claim_number) : t("claimNo") + " —"} · ${items.length} ${t("items")}`}
          action={
            <div className="flex flex-wrap gap-2">
              <Btn variant="outline" onClick={() => { setSelected(null); load(); }} data-testid="claim-back"><ChevronLeft className="w-4 h-4" />{t("backToPackets")}</Btn>
              <Btn variant="outline" onClick={() => openEdit(selected)} data-testid="claim-edit-detail"><Pencil className="w-4 h-4" />{t("edit")}</Btn>
              <Btn variant="outline" onClick={() => { setSendTo(""); setSendOpen(true); }} data-testid="claim-send"><Send className="w-4 h-4" />{t("send")}</Btn>
              <Btn onClick={() => { api.post(`/claims/${selected.id}/to-folder`).then((r) => toast.success(t("savedToFolder"))).catch(() => {}); authedDownload(`/claims/${selected.id}/merged`, "claim_packet.pdf"); setTimeout(() => refreshSelected(selected.id), 800); }} data-testid="claim-download-merged"><Download className="w-4 h-4" />{t("mergeSavePdf")}</Btn>
            </div>} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("patient")}</p>
            <p className="mt-1 text-moneygreen-800 font-semibold">{selected.patient_name || "—"}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("packetStatus")}</p>
            <div className="mt-1"><Badge tone={statusTone(selected.status)}>{t(selected.status)}</Badge></div>
          </Card>
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("createdBy")}</p>
            <p className="mt-1 text-stone-600 text-sm">{selected.created_by || "—"}</p>
          </Card>
        </div>
        {selected.notes && <Card className="p-4 mb-5"><p className="text-sm text-stone-600 whitespace-pre-wrap">{selected.notes}</p></Card>}

        {/* Add-to-packet toolbar */}
        <Card className="p-4 mb-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("attachExistingForm")}</label>
              <div className="flex gap-2 mt-1.5">
                <select value={pickForm} onChange={(e) => setPickForm(e.target.value)} className={inputCls} data-testid="claim-pick-form">
                  <option value="">{t("selectForm")}</option>
                  {forms.map((f) => <option key={f.id} value={f.id}>{f.title} · {f.patient_name}</option>)}
                </select>
                <Btn variant="outline" onClick={attachForm} disabled={!pickForm} data-testid="claim-attach-form" className="!px-3"><Plus className="w-4 h-4" /></Btn>
              </div>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("attachInvoice")}</label>
              <div className="flex gap-2 mt-1.5">
                <select value={pickInvoice} onChange={(e) => setPickInvoice(e.target.value)} className={inputCls} data-testid="claim-pick-invoice">
                  <option value="">{t("selectInvoice")}</option>
                  {invoices.map((i) => <option key={i.id} value={i.id}>{i.invoice_number} · {i.patient_name} · ${i.total}</option>)}
                </select>
                <Btn variant="outline" onClick={attachInvoice} disabled={!pickInvoice} data-testid="claim-attach-invoice" className="!px-3"><Plus className="w-4 h-4" /></Btn>
              </div>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("uploadDocument")}</label>
              <div className="mt-1.5">
                <input ref={fileRef} type="file" onChange={onUpload} data-testid="claim-upload-input"
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.txt,.xls,.xlsx"
                  className="block w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer disabled:opacity-60"
                  disabled={busy} />
              </div>
            </div>
          </div>
          <p className="text-xs text-stone-400 mt-3">{t("mergeHint")}</p>
        </Card>

        {/* Items list */}
        <Card className="overflow-hidden">
          {items.length === 0 ? <Empty text={t("noItemsYet")} /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="px-5 py-3">{t("itemSource")}</th>
                    <th className="px-5 py-3">{t("filename")}</th>
                    <th className="px-5 py-3 text-right">{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, i) => {
                    const Icon = sourceIcon[it.source] || FileText;
                    return (
                      <motion.tr key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                        data-testid={`claim-item-${it.id}`}
                        className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                        <td className="px-5 py-3"><Badge tone={sourceTone[it.source] || "gray"}>{t(`src_${it.source}`)}</Badge></td>
                        <td className="px-5 py-3 text-stone-700"><span className="inline-flex items-center gap-2"><Icon className="w-4 h-4 text-stone-400" />{it.filename}</span></td>
                        <td className="px-5 py-3">
                          <div className="flex justify-end items-center gap-1">
                            <div className="flex flex-col mr-1">
                              <button onClick={() => reorderItem(i, -1)} disabled={i === 0} data-testid={`claim-item-up-${it.id}`} className="text-stone-400 hover:text-moneygreen-600 disabled:opacity-30" title={t("moveUp")}><ArrowUp className="w-3.5 h-3.5" /></button>
                              <button onClick={() => reorderItem(i, 1)} disabled={i === items.length - 1} data-testid={`claim-item-down-${it.id}`} className="text-stone-400 hover:text-moneygreen-600 disabled:opacity-30" title={t("moveDown")}><ArrowDown className="w-3.5 h-3.5" /></button>
                            </div>
                            <Btn variant="ghost" onClick={() => previewItem(it)} data-testid={`claim-item-view-${it.id}`} className="!px-2" title={t("view")}><Eye className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => setRenameItem({ id: it.id, filename: it.filename })} data-testid={`claim-item-edit-${it.id}`} className="!px-2" title={t("edit")}><Pencil className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => moveItemToFolder(it)} data-testid={`claim-item-move-${it.id}`} className="!px-2 !text-moneygreen-700" title={t("moveToFolderTitle")}><FolderInput className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => authedDownload(`/claims/${selected.id}/items/${it.id}/download`, it.filename)} data-testid={`claim-item-download-${it.id}`} className="!px-2" title={t("saveAsPdf")}><Download className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => removeItem(it.id)} data-testid={`claim-item-remove-${it.id}`} className="!px-2 !text-destructive" title={t("removeFromPacket")}><Trash2 className="w-4 h-4" /></Btn>
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

        <PacketModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing}
          form={form} set={set} save={save} patients={patients} t={t}
          setClaimPatient={setClaimPatient} setClaimDate={setClaimDate} />

        <Modal open={!!preview} onClose={closePreview} title={preview?.label || t("preview")} wide>
          {preview && (
            <div className="rounded-lg overflow-hidden border border-border bg-stone-50">
              {preview.kind === "img"
                ? <img src={preview.url} alt={preview.label} className="max-h-[70vh] w-auto mx-auto" />
                : <iframe title={preview.label} src={preview.url} className="w-full h-[70vh]" />}
            </div>
          )}
        </Modal>

        <Modal open={!!renameItem} onClose={() => setRenameItem(null)} title={t("rename")}>
          {renameItem && (
            <form onSubmit={saveRename} className="space-y-4">
              <Field label={t("filename")}>
                <input required value={renameItem.filename} onChange={(e) => setRenameItem({ ...renameItem, filename: e.target.value })} className={inputCls} data-testid="claim-item-rename-input" />
              </Field>
              <div className="flex justify-end gap-2 pt-2">
                <Btn variant="outline" type="button" onClick={() => setRenameItem(null)}>{t("cancel")}</Btn>
                <Btn type="submit" data-testid="claim-item-rename-save">{t("save")}</Btn>
              </div>
            </form>
          )}
        </Modal>

        <Modal open={sendOpen} onClose={() => setSendOpen(false)} title={t("sendMergedPacket")}>
          <form onSubmit={sendPacket} className="space-y-4">
            <p className="text-sm text-stone-500">{t("sendPacketHint")}</p>
            <Field label={t("recipientEmail")}>
              <input type="email" required value={sendTo} onChange={(e) => setSendTo(e.target.value)} className={inputCls} data-testid="claim-send-input" placeholder="recipient@email.com" />
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setSendOpen(false)}>{t("cancel")}</Btn>
              <Btn type="submit" disabled={sendBusy || !sendTo} data-testid="claim-send-submit"><Send className="w-4 h-4" />{t("send")}</Btn>
            </div>
          </form>
        </Modal>
      </div>
    );
  }

  // ---------- List view ----------
  return (
    <div data-testid="claims-page">
      <PageHeader title={t("claims")} subtitle={t("claimsSubtitle")}
        action={
          <div className="flex flex-wrap gap-2">
            <Btn variant="outline" onClick={() => setFromDateOpen(true)} data-testid="build-from-date-btn"><CalendarClock className="w-4 h-4" />{t("buildFromDate")}</Btn>
            <Btn onClick={openNew} data-testid="new-claim-btn"><FilePlus className="w-4 h-4" />{t("newClaim")}</Btn>
          </div>} />

      <Card className="overflow-hidden">
        {packets.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("claimName")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("patient")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("claimNo")}</th>
                  <th className="px-5 py-3">{t("items")}</th>
                  <th className="px-5 py-3">{t("packetStatus")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {packets.map((p, i) => (
                  <motion.tr key={p.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`claim-row-${p.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 cursor-pointer ${p.status === "complete" ? "bg-moneygreen-50" : (i % 2 ? "bg-tan-50/40" : "")}`}
                    onClick={() => refreshSelected(p.id)}>
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center gap-2 font-semibold text-moneygreen-800"><FolderArchive className={`w-4 h-4 ${p.status === "complete" ? "text-moneygreen-600" : "text-moneygreen-500"}`} />{p.name}</span>
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{p.patient_name || "—"}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-500 font-mono text-xs">{fmtDate(p.claim_number) || "—"}</td>
                    <td className="px-5 py-3 text-stone-600">{(p.items || []).length}</td>
                    <td className="px-5 py-3"><Badge tone={statusTone(p.status)}>{t(p.status)}</Badge></td>
                    <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <Btn variant="outline" onClick={() => refreshSelected(p.id)} data-testid={`claim-open-${p.id}`}>{t("view")}</Btn>
                        <Btn variant="ghost" onClick={() => openEdit(p)} data-testid={`claim-edit-${p.id}`} className="!px-2"><Pencil className="w-4 h-4" /></Btn>
                        <Btn variant="ghost" onClick={() => remove(p.id)} data-testid={`claim-delete-${p.id}`} className="!px-2 !text-destructive"><Trash2 className="w-4 h-4" /></Btn>
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <PacketModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing}
        form={form} set={set} save={save} patients={patients} t={t}
        setClaimPatient={setClaimPatient} setClaimDate={setClaimDate} />

      <Modal open={fromDateOpen} onClose={() => setFromDateOpen(false)} title={t("buildFromDateTitle")}>
        <form onSubmit={buildFromDate} className="space-y-4">
          <p className="text-sm text-stone-500">{t("buildFromDateHint")}</p>
          <Field label={t("patient")}>
            <select required value={fromDate.patient_id} onChange={(e) => setFromDate((f) => ({ ...f, patient_id: e.target.value }))} className={inputCls} data-testid="fd-patient">
              <option value="">{t("selectPatient")}</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label={t("serviceDate")}>
            <input required type="date" value={fromDate.date} onChange={(e) => setFromDate((f) => ({ ...f, date: e.target.value }))} className={inputCls} data-testid="fd-date" />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setFromDateOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" disabled={building || !fromDate.patient_id || !fromDate.date} data-testid="fd-build-btn">{t("build")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function PacketModal({ open, onClose, editing, form, set, save, patients, t, setClaimPatient, setClaimDate }) {
  return (
    <Modal open={open} onClose={onClose} title={editing ? t("editClaim") : t("newClaim")}>
      <form onSubmit={save} className="space-y-4">
        <Field label={t("patient")}>
          <select value={form.patient_id} onChange={setClaimPatient} className={inputCls} data-testid="cf-patient">
            <option value="">{t("selectPatient")}</option>
            {patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("claimNo")}><input type="date" value={form.claim_number} onChange={setClaimDate} className={inputCls} data-testid="cf-number" /></Field>
          <Field label={t("packetStatus")}>
            <select value={form.status} onChange={set("status")} className={inputCls} data-testid="cf-status">
              <option value="draft">{t("draft")}</option>
              <option value="submitted">{t("submitted")}</option>
              <option value="complete">{t("complete")}</option>
            </select>
          </Field>
        </div>
        <Field label={t("claimName")}><input required value={form.name} onChange={set("name")} className={inputCls} data-testid="cf-name" /></Field>
        <Field label={t("extraNotes")}><textarea rows={3} value={form.notes} onChange={set("notes")} className={inputCls} data-testid="cf-notes" /></Field>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="outline" type="button" onClick={onClose}>{t("cancel")}</Btn>
          <Btn type="submit" data-testid="save-claim-btn">{t("save")}</Btn>
        </div>
      </form>
    </Modal>
  );
}
