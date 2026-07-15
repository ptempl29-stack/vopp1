import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Field, inputCls, Btn, Card } from "../components/ui-kit";
import { UserPlus, ChevronLeft, RefreshCw, Copy, CheckCircle2, Wand2 } from "lucide-react";
import { toast } from "sonner";

const ALL_TABS = ["dashboard", "patients", "appointments", "telehealth", "notes",
  "invoices", "cpt", "reports", "forms", "messages", "team", "audit", "claims", "assistant"];

function genPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
  const specials = "!@#$%&*";
  let p = "";
  for (let i = 0; i < 10; i++) p += chars[Math.floor(Math.random() * chars.length)];
  return p + specials[Math.floor(Math.random() * specials.length)] + Math.floor(Math.random() * 10);
}

const blank = {
  name: "", email: "", role: "receptionist", password: genPassword(),
  require_password_change: true, phone: "", title: "", license_number: "", doxy_room: "",
};

export default function StaffEnrollment() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [roles, setRoles] = useState([]);
  const [defaults, setDefaults] = useState({});
  const [form, setForm] = useState(blank);
  const [tabs, setTabs] = useState([]);
  const [done, setDone] = useState(null);

  useEffect(() => {
    api.get("/meta/tabs").then((r) => {
      setRoles(r.data.roles); setDefaults(r.data.defaults);
      setTabs(r.data.defaults[blank.role] || []);
    }).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const onRole = (e) => {
    const role = e.target.value;
    setForm({ ...form, role });
    setTabs(defaults[role] || []);
  };
  const toggleTab = (tab) => setTabs((prev) => prev.includes(tab) ? prev.filter((x) => x !== tab) : [...prev, tab]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/auth/register", { ...form, allowed_tabs: tabs });
      toast.success(t("enrollSuccess"));
      setDone({ email: form.email, password: form.password, name: form.name });
    } catch (err) { toast.error(apiErr(err)); }
  };

  const reset = () => { const f = { ...blank, password: genPassword() }; setForm(f); setTabs(defaults[f.role] || []); setDone(null); };

  if (done) {
    const creds = `${done.name}\nEmail: ${done.email}\nTemporary password: ${done.password}`;
    return (
      <div data-testid="enroll-success">
        <PageHeader title={t("enrollStaff")} subtitle={t("enrollSubtitle")} />
        <Card className="p-8 max-w-lg">
          <div className="w-12 h-12 rounded-full bg-moneygreen-100 flex items-center justify-center text-moneygreen-600 mb-4"><CheckCircle2 className="w-6 h-6" /></div>
          <h3 className="font-heading text-xl font-bold text-moneygreen-800">{done.name}</h3>
          <p className="text-sm text-stone-500 mt-1 mb-4">{t("credentialsReady")}</p>
          <div className="rounded-md bg-tan-50 border border-border p-4 space-y-1 font-mono text-sm text-moneygreen-800">
            <div>{done.email}</div>
            <div>{done.password}</div>
          </div>
          <div className="flex flex-wrap gap-2 mt-5">
            <Btn variant="outline" onClick={() => { navigator.clipboard.writeText(creds); toast.success(t("credsCopied")); }} data-testid="copy-credentials"><Copy className="w-4 h-4" />{t("copyCredentials")}</Btn>
            <Btn variant="outline" onClick={reset} data-testid="enroll-another"><UserPlus className="w-4 h-4" />{t("enrollAnother")}</Btn>
            <Btn onClick={() => navigate("/settings")} data-testid="back-to-admin"><ChevronLeft className="w-4 h-4" />{t("backToAdmin")}</Btn>
          </div>
        </Card>
      </div>
    );
  }

  const roleList = (roles.length ? roles : ["admin", "doctor", "nurse", "psychologist", "receptionist", "biller"]);

  return (
    <div data-testid="staff-enrollment-page">
      <PageHeader title={t("enrollStaff")} subtitle={t("enrollSubtitle")}
        action={<Btn variant="outline" onClick={() => navigate("/settings")} data-testid="enroll-back"><ChevronLeft className="w-4 h-4" />{t("backToAdmin")}</Btn>} />

      <form onSubmit={submit} className="space-y-5 max-w-3xl">
        <Card className="p-6">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-4">{t("accountSection")}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label={t("fullName")}><input required value={form.name} onChange={set("name")} className={inputCls} data-testid="en-name" /></Field>
            <Field label={t("email")}><input type="email" required value={form.email} onChange={set("email")} className={inputCls} data-testid="en-email" /></Field>
            <Field label={t("role")}>
              <select value={form.role} onChange={onRole} className={inputCls} data-testid="en-role">
                {roleList.map((r) => <option key={r} value={r}>{r === "admin" ? "CEO" : r}</option>)}
              </select>
            </Field>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-1">{t("accessSection")}</h3>
          <p className="text-xs text-stone-400 mb-3">{t("tabAccess")}</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2" data-testid="en-tabs-checklist">
            {ALL_TABS.map((tab) => (
              <label key={tab} className="flex items-center gap-2 px-3 py-2 rounded-md border border-border cursor-pointer hover:bg-tan-50 transition-colors duration-200">
                <input type="checkbox" checked={tabs.includes(tab)} onChange={() => toggleTab(tab)} data-testid={`en-tab-${tab}`} className="w-4 h-4 accent-moneygreen-600" />
                <span className="text-sm capitalize text-moneygreen-800">{tab}</span>
              </label>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-4">{t("credentialsSection")}</h3>
          <Field label={t("tempPassword")}>
            <div className="flex gap-2">
              <input required minLength={6} value={form.password} onChange={set("password")} className={inputCls} data-testid="en-password" />
              <Btn type="button" variant="outline" onClick={() => setForm({ ...form, password: genPassword() })} data-testid="en-generate" className="!px-3"><Wand2 className="w-4 h-4" />{t("generate")}</Btn>
            </div>
          </Field>
          <label className="flex items-center gap-2 mt-3 cursor-pointer">
            <input type="checkbox" checked={form.require_password_change} onChange={(e) => setForm({ ...form, require_password_change: e.target.checked })}
              data-testid="en-require-change" className="w-4 h-4 accent-moneygreen-600" />
            <span className="text-sm text-stone-600">{t("requirePwChangeCreate")}</span>
          </label>
        </Card>

        <Card className="p-6">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-4">{t("profileSection")}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label={t("phone")}><input value={form.phone} onChange={set("phone")} className={inputCls} data-testid="en-phone" /></Field>
            <Field label={t("professionalTitle")}><input value={form.title} onChange={set("title")} className={inputCls} data-testid="en-title" placeholder="MD, RN, LCSW…" /></Field>
            <Field label={t("licenseNumber")}><input value={form.license_number} onChange={set("license_number")} className={inputCls} data-testid="en-license" /></Field>
            <Field label={t("doxyRoom")}><input value={form.doxy_room} onChange={set("doxy_room")} className={inputCls} data-testid="en-doxy" placeholder="dr-lastname" /></Field>
          </div>
        </Card>

        <div className="flex justify-end gap-2">
          <Btn variant="outline" type="button" onClick={() => navigate("/settings")}>{t("cancel")}</Btn>
          <Btn type="submit" data-testid="enroll-submit"><UserPlus className="w-4 h-4" />{t("enrollStaff")}</Btn>
        </div>
      </form>
    </div>
  );
}
