import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useAuth } from "../context/AuthContext";
import { usePrivacy, Private } from "../context/PrivacyContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { fmtDate } from "../lib/date";
import { Plus, Search, Pencil, Trash2, Eye, Video, MapPin, CalendarClock, FileText, ClipboardList } from "lucide-react";
import { toast } from "sonner";

const blank = { first_name: "", last_name: "", dob: "", gender: "", ssn: "", phone: "", email: "", address: "", notes: "", status: "active" };

export default function Patients() {
  const { t } = useLang();
  const { user } = useAuth();
  const allowed = can(user?.role, "patients");
  const [patients, setPatients] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [history, setHistory] = useState({ appts: [], notes: [], forms: [] });
  const [loadingHist, setLoadingHist] = useState(false);
  const [provFilter, setProvFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const load = () => api.get("/patients", { params: { search } }).then((r) => setPatients(r.data)).catch(() => {});
  useEffect(() => { const d = setTimeout(load, 250); return () => clearTimeout(d); }, [search]);

  const openNew = () => { setForm(blank); setEditId(null); setOpen(true); };
  const openEdit = (p) => { setForm(p); setEditId(p.id); setOpen(true); };

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editId) await api.put(`/patients/${editId}`, form);
      else await api.post("/patients", form);
      toast.success(t("save") + " ✓");
      setOpen(false); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const remove = async (id) => {
    try { await api.delete(`/patients/${id}`); toast.success(t("delete") + " ✓"); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const openDetail = async (p) => {
    setDetail(p); setProvFilter(""); setTypeFilter("");
    setHistory({ appts: [], notes: [], forms: [] });
    setLoadingHist(true);
    const [appts, notes, forms] = await Promise.all([
      api.get("/appointments", { params: { patient_id: p.id } }).then((r) => r.data).catch(() => []),
      api.get("/notes", { params: { patient_id: p.id } }).then((r) => r.data).catch(() => []),
      api.get("/forms").then((r) => r.data.filter((f) => f.patient_id === p.id)).catch(() => []),
    ]);
    setHistory({ appts, notes, forms });
    setLoadingHist(false);
  };

  const provOptions = [...new Set(history.appts.map((a) => a.provider).filter(Boolean))];
  const filteredAppts = history.appts.filter((a) =>
    (!provFilter || a.provider === provFilter) &&
    (!typeFilter || (a.appointment_type || "in_person") === typeFilter));
  const filteredNotes = history.notes.filter((n) =>
    (!provFilter || n.attending_provider === provFilter || n.author === provFilter));

  return (
    <div>
      <PageHeader title={t("patients")} subtitle={`${patients.length} ${t("patients").toLowerCase()}`}
        action={allowed && <Btn onClick={openNew} data-testid="add-patient-btn"><Plus className="w-4 h-4" />{t("addPatient")}</Btn>} />

      <div className="relative mb-4 max-w-sm">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("search")}
          data-testid="patient-search"
          className={inputCls + " pl-9"} />
      </div>

      <Card className="overflow-hidden">
        {patients.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("name")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("phone")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("dob")}</th>
                  <th className="px-5 py-3">{t("status")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {patients.map((p, i) => (
                  <motion.tr key={p.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`patient-row-${p.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3">
                      <p className="font-semibold text-moneygreen-800"><Private value={`${p.first_name} ${p.last_name}`} /></p>
                      <p className="text-xs text-stone-500">{p.email || "—"}</p>
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{p.phone || "—"}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600"><Private value={fmtDate(p.dob)} /></td>
                    <td className="px-5 py-3"><Badge tone={p.status === "active" ? "green" : "gray"}>{t(p.status === "active" ? "active" : "inactive")}</Badge></td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        <Btn variant="ghost" onClick={() => openDetail(p)} data-testid={`view-patient-${p.id}`} className="!px-2"><Eye className="w-4 h-4" /></Btn>
                        {allowed ? (<>
                          <Btn variant="ghost" onClick={() => openEdit(p)} data-testid={`edit-patient-${p.id}`} className="!px-2"><Pencil className="w-4 h-4" /></Btn>
                          <Btn variant="ghost" onClick={() => remove(p.id)} data-testid={`delete-patient-${p.id}`} className="!px-2 !text-destructive"><Trash2 className="w-4 h-4" /></Btn>
                        </>) : null}
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title={editId ? t("edit") : t("newPatient")}>
        <form onSubmit={save} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("firstName")}><input required value={form.first_name} onChange={set("first_name")} className={inputCls} data-testid="pf-first" /></Field>
            <Field label={t("lastName")}><input required value={form.last_name} onChange={set("last_name")} className={inputCls} data-testid="pf-last" /></Field>
            <Field label={t("dob")}><input type="date" value={form.dob || ""} onChange={set("dob")} className={inputCls} data-testid="pf-dob" /></Field>
            <Field label={t("gender")}>
              <select value={form.gender || ""} onChange={set("gender")} className={inputCls}>
                <option value="">—</option><option value="male">M</option><option value="female">F</option><option value="other">X</option>
              </select>
            </Field>
            <Field label={t("phone")}><input value={form.phone || ""} onChange={set("phone")} className={inputCls} /></Field>
            <Field label={t("email")}><input value={form.email || ""} onChange={set("email")} className={inputCls} /></Field>
            <Field label={t("socialSecurity")}><input value={form.ssn || ""} onChange={set("ssn")} className={inputCls} data-testid="pf-ssn" placeholder="XXX-XX-XXXX" /></Field>
          </div>
          <Field label={t("address")}><input value={form.address || ""} onChange={set("address")} className={inputCls} /></Field>
          <Field label={t("status")}>
            <select value={form.status} onChange={set("status")} className={inputCls}>
              <option value="active">{t("active")}</option><option value="inactive">{t("inactive")}</option>
            </select>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-patient-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? `${detail.first_name} ${detail.last_name} — ${t("patientHistory")}` : ""} wide>
        {detail && (
          <div className="space-y-5" data-testid="patient-detail">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 rounded-md bg-tan-50 border border-border">
                <p className="text-xs text-stone-500">{t("dob")}</p><p className="font-semibold text-moneygreen-800"><Private value={fmtDate(detail.dob)} /></p>
              </div>
              <div className="p-3 rounded-md bg-tan-50 border border-border">
                <p className="text-xs text-stone-500">{t("socialSecurity")}</p><p className="font-semibold text-moneygreen-800"><Private value={detail.ssn} /></p>
              </div>
              <div className="p-3 rounded-md bg-tan-50 border border-border">
                <p className="text-xs text-stone-500">{t("phone")}</p><p className="font-semibold text-moneygreen-800">{detail.phone || "—"}</p>
              </div>
              <div className="p-3 rounded-md bg-tan-50 border border-border">
                <p className="text-xs text-stone-500">{t("status")}</p><p className="font-semibold text-moneygreen-800 capitalize">{t(detail.status === "active" ? "active" : "inactive")}</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-stone-500">{t("filterBy")}:</span>
              <select value={provFilter} onChange={(e) => setProvFilter(e.target.value)} data-testid="detail-filter-provider" className={inputCls + " !w-auto"}>
                <option value="">{t("allProviders")}</option>
                {provOptions.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} data-testid="detail-filter-type" className={inputCls + " !w-auto"}>
                <option value="">{t("allTypes")}</option>
                <option value="in_person">{t("inPerson")}</option>
                <option value="telehealth">{t("telehealth")}</option>
              </select>
            </div>

            {loadingHist ? <p className="text-sm text-stone-400 py-6 text-center">…</p> : (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <Section icon={CalendarClock} title={`${t("appointmentsCount")} (${filteredAppts.length})`} testid="detail-appts">
                  {filteredAppts.length === 0 ? <Empty text={t("noRecords")} /> : filteredAppts.map((a) => (
                    <div key={a.id} className="p-2.5 rounded-md border border-border text-sm" data-testid={`detail-appt-${a.id}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-moneygreen-800">{fmtDate(a.date)} {a.time && `· ${a.time}`}</span>
                        <Badge tone={(a.appointment_type || "in_person") === "telehealth" ? "green" : "tan"} className="flex items-center gap-1">
                          {(a.appointment_type || "in_person") === "telehealth" ? <Video className="w-3 h-3" /> : <MapPin className="w-3 h-3" />}
                          {(a.appointment_type || "in_person") === "telehealth" ? t("telehealth") : t("inPerson")}
                        </Badge>
                      </div>
                      <p className="text-stone-500">{a.provider || "—"}</p>
                      {a.reason && <p className="text-stone-400 text-xs line-clamp-1">{a.reason}</p>}
                    </div>
                  ))}
                </Section>
                <Section icon={FileText} title={`${t("notesCount")} (${filteredNotes.length})`} testid="detail-notes">
                  {filteredNotes.length === 0 ? <Empty text={t("noRecords")} /> : filteredNotes.map((n) => (
                    <div key={n.id} className="p-2.5 rounded-md border border-border text-sm" data-testid={`detail-note-${n.id}`}>
                      <p className="font-semibold text-moneygreen-800 line-clamp-1">{n.title}</p>
                      <p className="text-stone-500 text-xs">{fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))} · {n.attending_provider || n.author}</p>
                    </div>
                  ))}
                </Section>
                <Section icon={ClipboardList} title={`${t("formsCount")} (${history.forms.length})`} testid="detail-forms">
                  {history.forms.length === 0 ? <Empty text={t("noRecords")} /> : history.forms.map((f) => (
                    <div key={f.id} className="p-2.5 rounded-md border border-border text-sm" data-testid={`detail-form-${f.id}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-moneygreen-800 line-clamp-1">{f.title}</span>
                        <Badge tone={f.status === "received" ? "green" : "amber"}>{t(f.status)}</Badge>
                      </div>
                      <p className="text-stone-500 text-xs">{f.form_type}</p>
                    </div>
                  ))}
                </Section>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

const Section = ({ icon: Icon, title, testid, children }) => (
  <div data-testid={testid}>
    <div className="flex items-center gap-2 mb-2 text-moneygreen-700">
      <Icon className="w-4 h-4" />
      <p className="text-xs font-bold uppercase tracking-wider">{title}</p>
    </div>
    <div className="space-y-2 max-h-72 overflow-y-auto custom-scroll pr-1">{children}</div>
  </div>
);
