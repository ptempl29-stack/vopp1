import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { Plus, Video, Trash2, Clock } from "lucide-react";
import { toast } from "sonner";

const blank = { patient_id: "", provider: "", date: "", time: "", reason: "", status: "scheduled" };
const toneMap = { scheduled: "green", completed: "gray", cancelled: "red" };

export default function Appointments() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [appts, setAppts] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);

  const load = () => api.get("/appointments").then((r) => setAppts(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = async (e) => {
    e.preventDefault();
    try { await api.post("/appointments", form); toast.success(t("save") + " ✓"); setOpen(false); setForm(blank); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const remove = async (id) => {
    try { await api.delete(`/appointments/${id}`); load(); } catch (err) { toast.error(apiErr(err)); }
  };

  return (
    <div>
      <PageHeader title={t("appointments")} subtitle={`${appts.length} ${t("appointments").toLowerCase()}`}
        action={<Btn onClick={() => { setForm(blank); setOpen(true); }} data-testid="add-appt-btn"><Plus className="w-4 h-4" />{t("newAppointment")}</Btn>} />

      {appts.length === 0 ? <Card><Empty text={t("noData")} /></Card> : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {appts.map((a, i) => (
            <motion.div key={a.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Card className="p-5" data-testid={`appt-card-${a.id}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-heading font-bold text-moneygreen-800">{a.patient_name}</p>
                    <p className="text-sm text-stone-500">{a.provider || "—"}</p>
                  </div>
                  <Badge tone={toneMap[a.status]}>{t(a.status)}</Badge>
                </div>
                <div className="flex items-center gap-2 text-sm text-stone-600 mb-1">
                  <Clock className="w-4 h-4 text-moneygreen-500" /> {a.date} {a.time && `· ${a.time}`}
                </div>
                <p className="text-sm text-stone-500 mb-4 line-clamp-2">{a.reason || "—"}</p>
                <div className="flex gap-2">
                  <Btn onClick={() => navigate(`/telehealth?room=vpp-${a.id}&name=${encodeURIComponent(a.patient_name)}`)}
                    data-testid={`join-video-${a.id}`} className="flex-1">
                    <Video className="w-4 h-4" />{t("joinVideo")}
                  </Btn>
                  <Btn variant="danger" onClick={() => remove(a.id)} data-testid={`delete-appt-${a.id}`} className="!px-3"><Trash2 className="w-4 h-4" /></Btn>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={t("newAppointment")}>
        <form onSubmit={save} className="space-y-4">
          <Field label={t("patient")}>
            <select required value={form.patient_id} onChange={set("patient_id")} className={inputCls} data-testid="af-patient">
              <option value="">—</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
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
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-appt-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
