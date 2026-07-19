import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import {
  FolderArchive, Plus, Pencil, Trash2, ChevronLeft, Download, FileText,
  ReceiptText, Upload, FilePlus,
} from "lucide-react";
import { toast } from "sonner";

const sourceIcon = { form: FileText, invoice: ReceiptText, upload: Upload };
const sourceTone = { form: "green", invoice: "amber", upload: "tan" };
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

  // ---------- Detail view ----------
  if (selected) {
    const items = selected.items || [];
    return (
      <div data-testid="claim-detail">
        <PageHeader title={selected.name}
          subtitle={`${selected.claim_number || t("claimNo") + " —"} · ${items.length} ${t("items")}`}
          action={
            <div className="flex flex-wrap gap-2">
              <Btn variant="outline" onClick={() => { setSelected(null); load(); }} data-testid="claim-back"><ChevronLeft className="w-4 h-4" />{t("backToPackets")}</Btn>
              <Btn variant="outline" onClick={() => openEdit(selected)} data-testid="claim-edit-detail"><Pencil className="w-4 h-4" />{t("edit")}</Btn>
              <Btn onClick={() => { api.post(`/claims/${selected.id}/to-folder`).then((r) => toast.success(t("savedToFolder"))).catch(() => {}); authedDownload(`/claims/${selected.id}/merged`, "claim_packet.pdf"); }} data-testid="claim-download-merged"><Download className="w-4 h-4" />{t("downloadMergedPdf")}</Btn>
            </div>} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("patient")}</p>
            <p className="mt-1 text-moneygreen-800 font-semibold">{selected.patient_name || "—"}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("packetStatus")}</p>
            <div className="mt-1"><Badge tone={selected.status === "submitted" ? "green" : "amber"}>{t(selected.status)}</Badge></div>
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
                          <div className="flex justify-end gap-1">
                            <Btn variant="ghost" onClick={() => authedDownload(`/claims/${selected.id}/items/${it.id}/download`, it.filename)} data-testid={`claim-item-download-${it.id}`} className="!px-2" title={t("download")}><Download className="w-4 h-4" /></Btn>
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
          form={form} set={set} save={save} patients={patients} t={t} />
      </div>
    );
  }

  // ---------- List view ----------
  return (
    <div data-testid="claims-page">
      <PageHeader title={t("claims")} subtitle={t("claimsSubtitle")}
        action={<Btn onClick={openNew} data-testid="new-claim-btn"><FilePlus className="w-4 h-4" />{t("newClaim")}</Btn>} />

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
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 cursor-pointer ${i % 2 ? "bg-tan-50/40" : ""}`}
                    onClick={() => refreshSelected(p.id)}>
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center gap-2 font-semibold text-moneygreen-800"><FolderArchive className="w-4 h-4 text-moneygreen-500" />{p.name}</span>
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{p.patient_name || "—"}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-500 font-mono text-xs">{p.claim_number || "—"}</td>
                    <td className="px-5 py-3 text-stone-600">{(p.items || []).length}</td>
                    <td className="px-5 py-3"><Badge tone={p.status === "submitted" ? "green" : "amber"}>{t(p.status)}</Badge></td>
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
        form={form} set={set} save={save} patients={patients} t={t} />
    </div>
  );
}

function PacketModal({ open, onClose, editing, form, set, save, patients, t }) {
  return (
    <Modal open={open} onClose={onClose} title={editing ? t("editClaim") : t("newClaim")}>
      <form onSubmit={save} className="space-y-4">
        <Field label={t("claimName")}><input required value={form.name} onChange={set("name")} className={inputCls} data-testid="cf-name" /></Field>
        <Field label={t("patient")}>
          <select value={form.patient_id} onChange={set("patient_id")} className={inputCls} data-testid="cf-patient">
            <option value="">{t("selectPatient")}</option>
            {patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("claimNo")}><input value={form.claim_number} onChange={set("claim_number")} className={inputCls} data-testid="cf-number" /></Field>
          <Field label={t("packetStatus")}>
            <select value={form.status} onChange={set("status")} className={inputCls} data-testid="cf-status">
              <option value="draft">{t("draft")}</option>
              <option value="submitted">{t("submitted")}</option>
            </select>
          </Field>
        </div>
        <Field label={t("extraNotes")}><textarea rows={3} value={form.notes} onChange={set("notes")} className={inputCls} data-testid="cf-notes" /></Field>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="outline" type="button" onClick={onClose}>{t("cancel")}</Btn>
          <Btn type="submit" data-testid="save-claim-btn">{t("save")}</Btn>
        </div>
      </form>
    </Modal>
  );
}
