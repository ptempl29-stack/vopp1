import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { UserPlus, Trash2, ShieldCheck, Pencil } from "lucide-react";
import { toast } from "sonner";

const ALL_TABS = ["dashboard", "patients", "appointments", "telehealth", "notes",
  "invoices", "cpt", "reports", "forms", "messages", "team"];

const roleColors = {
  doctor: "green", nurse: "green", psychologist: "green",
  receptionist: "tan", biller: "gray", admin: "green",
};

export default function Team() {
  const { t } = useLang();
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [defaults, setDefaults] = useState({});
  const [addOpen, setAddOpen] = useState(false);
  const [editUser, setEditUser] = useState(null);
  const [editTabs, setEditTabs] = useState([]);
  const [infoUser, setInfoUser] = useState(null);
  const [infoForm, setInfoForm] = useState({ name: "", email: "", role: "", password: "" });
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "receptionist" });

  const load = () => api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/meta/tabs").then((r) => { setRoles(r.data.roles); setDefaults(r.data.defaults); }).catch(() => {});
  }, []);

  const createUser = async (e) => {
    e.preventDefault();
    try {
      await api.post("/auth/register", form);
      toast.success(t("createUser") + " ✓");
      setAddOpen(false); setForm({ name: "", email: "", password: "", role: "receptionist" }); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const openTabs = (u) => { setEditUser(u); setEditTabs(u.allowed_tabs || []); };
  const toggleTab = (tab) => setEditTabs((prev) => prev.includes(tab) ? prev.filter((x) => x !== tab) : [...prev, tab]);
  const saveTabs = async () => {
    try {
      await api.put(`/users/${editUser.id}/tabs`, { allowed_tabs: editTabs });
      toast.success(t("saveAccess") + " ✓");
      setEditUser(null); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const removeUser = async (id) => {
    try { await api.delete(`/users/${id}`); toast.success(t("deleteUser") + " ✓"); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const openInfo = (u) => { setInfoUser(u); setInfoForm({ name: u.name, email: u.email, role: u.role, password: "" }); };
  const saveInfo = async (e) => {
    e.preventDefault();
    const payload = { name: infoForm.name, email: infoForm.email, role: infoForm.role };
    if (infoForm.password) payload.password = infoForm.password;
    try {
      await api.put(`/users/${infoUser.id}`, payload);
      toast.success(t("save") + " ✓");
      setInfoUser(null); load();
    } catch (err) { toast.error(apiErr(err)); }
  };
  const setInfo = (k) => (e) => setInfoForm({ ...infoForm, [k]: e.target.value });

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div>
      <PageHeader title={t("team")} subtitle={t("teamSubtitle")}
        action={<Btn onClick={() => setAddOpen(true)} data-testid="add-user-btn"><UserPlus className="w-4 h-4" />{t("addUser")}</Btn>} />

      <Card className="overflow-hidden">
        {users.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("name")}</th>
                  <th className="px-5 py-3">{t("role")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("tabAccess")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <motion.tr key={u.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`user-row-${u.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3">
                      <p className="font-semibold text-moneygreen-800">{u.name}</p>
                      <p className="text-xs text-stone-500">{u.email}</p>
                    </td>
                    <td className="px-5 py-3"><Badge tone={roleColors[u.role] || "gray"}>{u.role}</Badge></td>
                    <td className="px-5 py-3 hidden md:table-cell">
                      <span className="text-xs text-stone-500">{(u.allowed_tabs || []).length} tabs</span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        <Btn variant="ghost" onClick={() => openInfo(u)} data-testid={`edit-user-${u.id}`} className="!px-2" title={t("edit")}>
                          <Pencil className="w-4 h-4" />
                        </Btn>
                        <Btn variant="outline" onClick={() => openTabs(u)} data-testid={`edit-tabs-${u.id}`}>
                          <ShieldCheck className="w-4 h-4" />{t("tabAccess")}
                        </Btn>
                        {u.id !== me.id && u.role !== "admin" && (
                          <Btn variant="ghost" onClick={() => removeUser(u.id)} data-testid={`delete-user-${u.id}`} className="!px-2 !text-destructive"><Trash2 className="w-4 h-4" /></Btn>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title={t("newUser")}>
        <form onSubmit={createUser} className="space-y-4">
          <Field label={t("fullName")}><input required value={form.name} onChange={set("name")} className={inputCls} data-testid="uf-name" /></Field>
          <Field label={t("email")}><input type="email" required value={form.email} onChange={set("email")} className={inputCls} data-testid="uf-email" /></Field>
          <Field label={t("password")}><input type="password" required minLength={6} value={form.password} onChange={set("password")} className={inputCls} data-testid="uf-password" /></Field>
          <Field label={t("role")}>
            <select value={form.role} onChange={set("role")} className={inputCls} data-testid="uf-role">
              {(roles.length ? roles : ["doctor", "nurse", "psychologist", "receptionist", "biller"]).filter((r) => r !== "admin").map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          <p className="text-xs text-stone-500">Default tabs for this role: {(defaults[form.role] || []).join(", ")}</p>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setAddOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-user-btn">{t("createUser")}</Btn>
          </div>
        </form>
      </Modal>

      <Modal open={!!editUser} onClose={() => setEditUser(null)} title={`${t("tabAccess")} — ${editUser?.name || ""}`}>
        {editUser && (
          <div>
            <div className="grid grid-cols-2 gap-2" data-testid="tabs-checklist">
              {ALL_TABS.map((tab) => (
                <label key={tab} className="flex items-center gap-2 px-3 py-2 rounded-md border border-border cursor-pointer hover:bg-tan-50 transition-colors duration-200">
                  <input type="checkbox" checked={editTabs.includes(tab)} onChange={() => toggleTab(tab)}
                    data-testid={`tab-${tab}`} className="w-4 h-4 accent-moneygreen-600" />
                  <span className="text-sm capitalize text-moneygreen-800">{tab}</span>
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Btn variant="outline" type="button" onClick={() => setEditUser(null)}>{t("cancel")}</Btn>
              <Btn onClick={saveTabs} data-testid="save-tabs-btn">{t("saveAccess")}</Btn>
            </div>
          </div>
        )}
      </Modal>
      <Modal open={!!infoUser} onClose={() => setInfoUser(null)} title={`${t("edit")} — ${infoUser?.name || ""}`}>
        {infoUser && (
          <form onSubmit={saveInfo} className="space-y-4">
            <Field label={t("fullName")}><input required value={infoForm.name} onChange={setInfo("name")} className={inputCls} data-testid="eu-name" /></Field>
            <Field label={t("email")}><input type="email" required value={infoForm.email} onChange={setInfo("email")} className={inputCls} data-testid="eu-email" /></Field>
            <Field label={t("role")}>
              <select value={infoForm.role} onChange={setInfo("role")} className={inputCls} data-testid="eu-role" disabled={infoUser.role === "admin"}>
                {(roles.length ? roles : ["doctor", "nurse", "psychologist", "receptionist", "biller", "admin"]).map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <Field label={t("password") + " (" + t("orLabel") + " leave blank)"}>
              <input type="password" minLength={6} value={infoForm.password} onChange={setInfo("password")} className={inputCls} data-testid="eu-password" placeholder="••••••" />
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setInfoUser(null)}>{t("cancel")}</Btn>
              <Btn type="submit" data-testid="save-user-info-btn">{t("save")}</Btn>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
