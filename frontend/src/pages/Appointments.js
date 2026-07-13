import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { Plus, Video, Trash2, Clock, MapPin, Filter, X } from "lucide-react";
import { toast } from "sonner";

const blank = { patient_id: "", provider: "", date: "", time: "", reason: "", appointment_type: "in_person", status: "scheduled" };
const toneMap = { scheduled: "green", completed: "gray", cancelled: "red" };
const today = () => new Date().toISOString().slice(0, 10);

export default function Appointments() {
  const { t } = useLang();
  const { user } = useAuth();
  const allowed = can(user?.role, "appointments");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [appts, setAppts] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const dateToday = params.get("date") === "today";
  const sel = useSelection();

  const load = () => api.get("/appointments").then((r) => setAppts(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
  }, []);

  const providers = useMemo(
    () => [...new Set(appts.map((a) => a.provider).filter(Boolean))], [appts]);

  const filtered = useMemo(() => appts.filter((a) =>
    (!typeFilter || (a.appointment_type || "in_person") === typeFilter) &&
    (!providerFilter || a.provider === providerFilter) &&
    (!dateToday || a.date === today())
  ), [appts, typeFilter, providerFilter, dateToday]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const openNew = () => { setForm(blank); setEditId(null); setOpen(true); };
  const openEdit = (a) => { setForm({ ...blank, ...a }); setEditId(a.id); setOpen(true); };

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editId) await api.put(`/appointments/${editId}`, form);
      else await api.post("/appointments", form);
      toast.success(t("save") + " ✓"); setOpen(false); setForm(blank); setEditId(null); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const remove = async (id) => {
    try { await api.delete(`/appointments/${id}`); load(); } catch (err) { toast.error(apiErr(err)); }
  };

  const removeSelected = async () => {
    try { await bulkDelete("/appointments/bulk-delete", [...sel.selected], t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const isTele = (a) => (a.appointment_type || "in_person") === "telehealth";

  return (
    <div>
      <PageHeader title={t("appointments")} subtitle={`${filtered.length} ${t("appointments").toLowerCase()}`}
        action={allowed && <Btn onClick={openNew} data-testid="add-appt-btn"><Plus className="w-4 h-4" />{t("newAppointment")}</Btn>} />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex items-center gap-1.5 text-stone-500 text-sm font-semibold"><Filter className="w-4 h-4" />{t("filterBy")}:</div>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} data-testid="filter-type"
          className={inputCls + " !w-auto"}>
          <option value="">{t("allTypes")}</option>
          <option value="in_person">{t("inPerson")}</option>
          <option value="telehealth">{t("telehealth")}</option>
        </select>
        <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} data-testid="filter-provider"
          className={inputCls + " !w-auto"}>
          <option value="">{t("allProviders")}</option>
          {providers.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        {dateToday && (
          <Badge tone="green" className="flex items-center gap-1">{t("apptToday")}
            <button onClick={() => { params.delete("date"); setParams(params); }} data-testid="clear-today-filter"><X className="w-3 h-3" /></button>
          </Badge>
        )}
        {sel.count > 0 && allowed && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm text-stone-500">{sel.count}</span>
            <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-appts"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
            <Btn variant="ghost" onClick={sel.clear} data-testid="clear-appt-selection">{t("clearSelection")}</Btn>
          </div>
        )}
      </div>

      {filtered.length === 0 ? <Card><Empty text={t("noData")} /></Card> : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((a, i) => (
            <motion.div key={a.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Card className={`p-5 ${sel.has(a.id) ? "ring-2 ring-moneygreen-500" : ""}`} data-testid={`appt-card-${a.id}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-start gap-2.5">
                    {allowed && (
                      <input type="checkbox" checked={sel.has(a.id)} onChange={() => sel.toggle(a.id)}
                        data-testid={`select-appt-${a.id}`} className="mt-1 w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                    )}
                    <div>
                      <p className="font-heading font-bold text-moneygreen-800">{a.patient_name}</p>
                      <p className="text-sm text-stone-500">{a.provider || "—"}</p>
                    </div>
                  </div>
                  <Badge tone={toneMap[a.status]}>{t(a.status)}</Badge>
                </div>
                <div className="flex items-center gap-2 mb-2">
                  <Badge tone={isTele(a) ? "green" : "tan"} data-testid={`appt-type-${a.id}`} className="flex items-center gap-1">
                    {isTele(a) ? <Video className="w-3 h-3" /> : <MapPin className="w-3 h-3" />}
                    {isTele(a) ? t("telehealth") : t("inPerson")}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 text-sm text-stone-600 mb-1">
                  <Clock className="w-4 h-4 text-moneygreen-500" /> {a.date} {a.time && `· ${a.time}`}
                </div>
                <p className="text-sm text-stone-500 mb-4 line-clamp-2">{a.reason || "—"}</p>
                <div className="flex gap-2">
                  {isTele(a) && (
                    <Btn onClick={() => navigate(`/telehealth?room=vpp-${a.id}&name=${encodeURIComponent(a.patient_name)}`)}
                      data-testid={`join-video-${a.id}`} className="flex-1">
                      <Video className="w-4 h-4" />{t("joinVideo")}
                    </Btn>
                  )}
                  {allowed && <Btn variant="outline" onClick={() => openEdit(a)} data-testid={`edit-appt-${a.id}`} className={isTele(a) ? "!px-3" : "flex-1"}>{t("edit")}</Btn>}
                  {allowed && <Btn variant="danger" onClick={() => remove(a.id)} data-testid={`delete-appt-${a.id}`} className="!px-3"><Trash2 className="w-4 h-4" /></Btn>}
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => { setOpen(false); setEditId(null); }} title={editId ? t("edit") : t("newAppointment")}>
        <form onSubmit={save} className="space-y-4">
          <Field label={t("patient")}>
            <select required value={form.patient_id} onChange={set("patient_id")} className={inputCls} data-testid="af-patient">
              <option value="">—</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </Field>
          <Field label={t("appointmentType")}>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => setForm({ ...form, appointment_type: "in_person" })} data-testid="af-type-in-person"
                className={`flex items-center justify-center gap-2 py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.appointment_type === "in_person" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                <MapPin className="w-4 h-4" />{t("inPerson")}
              </button>
              <button type="button" onClick={() => setForm({ ...form, appointment_type: "telehealth" })} data-testid="af-type-telehealth"
                className={`flex items-center justify-center gap-2 py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.appointment_type === "telehealth" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                <Video className="w-4 h-4" />{t("telehealth")}
              </button>
            </div>
          </Field>
          <Field label={t("provider")}><input value={form.provider} onChange={set("provider")} className={inputCls} placeholder="Dr. …" /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("date")}><input type="date" required value={form.date} onChange={set("date")} className={inputCls} data-testid="af-date" /></Field>
            <Field label={t("time")}><input type="time" value={form.time} onChange={set("time")} className={inputCls} /></Field>
          </div>
          <Field label={t("reason")}><textarea value={form.reason} onChange={set("reason")} className={inputCls} rows={2} /></Field>
          <Field label={t("status")}>
            <select value={form.status} onChange={set("status")} className={inputCls}>
              <option value="scheduled">{t("scheduled")}</option><option value="completed">{t("completed")}</option><option value="cancelled">{t("cancelled")}</option>
            </select>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => { setOpen(false); setEditId(null); }}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-appt-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
