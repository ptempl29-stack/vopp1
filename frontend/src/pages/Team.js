import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { UserPlus, Trash2, ShieldCheck, Pencil, FileSignature, Mail, Copy, Link2, Send } from "lucide-react";
import { toast } from "sonner";

const ALL_TABS = ["dashboard", "patients", "appointments", "telehealth", "notes",
  "invoices", "cpt", "reports", "forms", "messages", "team", "audit", "claims", "assistant"];

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
  const [lhOpen, setLhOpen] = useState(false);
  const [lh, setLh] = useState({ clinic_name: "", tagline: "", address: "", phone: "", email: "", logo: "" });
  const [invites, setInvites] = useState([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "receptionist", allowed_tabs: [] });
  const [createdLink, setCreatedLink] = useState("");

  const loadInvites = () => api.get("/invites").then((r) => setInvites(r.data)).catch(() => {});
  const inviteUrl = (tok) => `${window.location.origin}/accept-invite/${tok}`;

  const openInvite = () => {
    setCreatedLink("");
    setInviteForm({ email: "", role: "receptionist", allowed_tabs: [] });
    setInviteOpen(true);
  };
  const onInviteRole = (e) => setInviteForm((f) => ({ ...f, role: e.target.value }));
  const toggleInviteTab = (tab) => setInviteForm((f) => ({
    ...f, allowed_tabs: f.allowed_tabs.includes(tab) ? f.allowed_tabs.filter((x) => x !== tab) : [...f.allowed_tabs, tab],
  }));
  const createInvite = async (e) => {
    e.preventDefault();
    try {
      const payload = { email: inviteForm.email, role: inviteForm.role,
        allowed_tabs: inviteForm.allowed_tabs.length ? inviteForm.allowed_tabs : null };
      const r = await api.post("/invites", payload);
      setCreatedLink(inviteUrl(r.data.token));
      toast.success(t("inviteCreated"));
      loadInvites();
    } catch (err) { toast.error(apiErr(err)); }
  };
  const copyInvite = (tok) => {
    navigator.clipboard.writeText(inviteUrl(tok))
      .then(() => toast.success(t("inviteCopied")))
      .catch(() => toast.error(inviteUrl(tok)));
  };
  const revokeInvite = async (id) => {
    try { await api.delete(`/invites/${id}`); loadInvites(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const openLetterhead = () => {
    api.get("/settings").then((r) => { setLh(r.data); setLhOpen(true); }).catch((e) => toast.error(apiErr(e)));
  };
  const onLogoFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 600000) { toast.error("Logo too large (max ~600KB)"); return; }
    const reader = new FileReader();
    reader.onload = () => setLh((s) => ({ ...s, logo: reader.result }));
    reader.readAsDataURL(file);
  };
  const saveLetterhead = async (e) => {
    e.preventDefault();
    try { await api.put("/settings", lh); toast.success(t("save") + " ✓"); setLhOpen(false); }
    catch (err) { toast.error(apiErr(err)); }
  };
  const setLhField = (k) => (e) => setLh({ ...lh, [k]: e.target.value });

  const load = () => api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
  useEffect(() => {
    load();
    loadInvites();
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
      <PageHeader title={t("settings")} subtitle={t("settingsSubtitle")}
        action={<div className="flex gap-2 flex-wrap">
          <Btn variant="outline" onClick={openLetterhead} data-testid="edit-letterhead-btn"><FileSignature className="w-4 h-4" />{t("letterhead")}</Btn>
          <Btn variant="outline" onClick={openInvite} data-testid="invite-staff-btn"><Mail className="w-4 h-4" />{t("inviteStaff")}</Btn>
          <Btn onClick={() => setAddOpen(true)} data-testid="add-user-btn"><UserPlus className="w-4 h-4" />{t("addUser")}</Btn>
        </div>} />

      <h3 className="font-heading text-lg font-bold text-moneygreen-800 mb-3">{t("staffMembers")}</h3>
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

      <div className="mt-8">
        <h3 className="font-heading text-lg font-bold text-moneygreen-800 mb-3">{t("invites")}</h3>
        <Card className="overflow-hidden">
          {invites.length === 0 ? <Empty text={t("noData")} /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="px-5 py-3">{t("email")}</th>
                    <th className="px-5 py-3">{t("role")}</th>
                    <th className="px-5 py-3">{t("status")}</th>
                    <th className="px-5 py-3 text-right">{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {invites.map((iv, i) => (
                    <tr key={iv.id} data-testid={`invite-row-${iv.id}`} className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                      <td className="px-5 py-3 text-moneygreen-800 font-medium">{iv.email}</td>
                      <td className="px-5 py-3"><Badge tone="tan">{iv.role}</Badge></td>
                      <td className="px-5 py-3"><Badge tone={iv.status === "accepted" ? "green" : "amber"}>{iv.status === "accepted" ? t("accepted") : t("pending")}</Badge></td>
                      <td className="px-5 py-3">
                        <div className="flex justify-end gap-1">
                          {iv.status === "pending" && (
                            <Btn variant="outline" onClick={() => copyInvite(iv.token)} data-testid={`copy-invite-${iv.id}`}><Copy className="w-4 h-4" />{t("copyInviteLink")}</Btn>
                          )}
                          <Btn variant="ghost" onClick={() => revokeInvite(iv.id)} data-testid={`revoke-invite-${iv.id}`} className="!px-2 !text-destructive" title={t("revoke")}><Trash2 className="w-4 h-4" /></Btn>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Modal open={inviteOpen} onClose={() => setInviteOpen(false)} title={t("inviteStaff")}>
        {createdLink ? (
          <div className="space-y-4" data-testid="invite-link-box">
            <p className="text-sm text-stone-600">{t("inviteHint")}</p>
            <div className="flex items-center gap-2 p-3 rounded-md bg-tan-50 border border-border">
              <Link2 className="w-4 h-4 text-moneygreen-600 shrink-0" />
              <span className="text-xs font-mono text-moneygreen-800 truncate flex-1" data-testid="invite-link-value">{createdLink}</span>
            </div>
            <div className="flex justify-end gap-2">
              <Btn variant="outline" onClick={() => { navigator.clipboard.writeText(createdLink); toast.success(t("inviteCopied")); }} data-testid="copy-created-invite"><Copy className="w-4 h-4" />{t("copyInviteLink")}</Btn>
              <Btn onClick={() => setInviteOpen(false)}>{t("cancel")}</Btn>
            </div>
          </div>
        ) : (
          <form onSubmit={createInvite} className="space-y-4">
            <Field label={t("email")}><input type="email" required value={inviteForm.email} onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })} className={inputCls} data-testid="invite-email" placeholder="employee@email.com" /></Field>
            <Field label={t("role")}>
              <select value={inviteForm.role} onChange={onInviteRole} className={inputCls} data-testid="invite-role">
                {(roles.length ? roles : ["doctor", "nurse", "psychologist", "receptionist", "biller"]).filter((r) => r !== "admin").map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <div>
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("tabAccess")}</label>
              <p className="text-xs text-stone-400 mt-1">{`Default: ${(defaults[inviteForm.role] || []).join(", ")}`}</p>
              <div className="grid grid-cols-2 gap-2 mt-2" data-testid="invite-tabs-checklist">
                {ALL_TABS.map((tab) => (
                  <label key={tab} className="flex items-center gap-2 px-3 py-2 rounded-md border border-border cursor-pointer hover:bg-tan-50 transition-colors duration-200">
                    <input type="checkbox" checked={inviteForm.allowed_tabs.includes(tab)} onChange={() => toggleInviteTab(tab)} data-testid={`invite-tab-${tab}`} className="w-4 h-4 accent-moneygreen-600" />
                    <span className="text-sm capitalize text-moneygreen-800">{tab}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-stone-400 mt-2">{t("inviteHint")}</p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setInviteOpen(false)}>{t("cancel")}</Btn>
              <Btn type="submit" data-testid="create-invite-btn"><Send className="w-4 h-4" />{t("sendInvite")}</Btn>
            </div>
          </form>
        )}
      </Modal>

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
      <Modal open={lhOpen} onClose={() => setLhOpen(false)} title={t("letterhead")}>
        <form onSubmit={saveLetterhead} className="space-y-4">
          <div className="flex items-center gap-4">
            {lh.logo ? <img src={lh.logo} alt="logo" className="h-16 w-16 object-contain rounded-md border border-border" data-testid="lh-logo-preview" />
              : <div className="h-16 w-16 rounded-md bg-moneygreen-100 flex items-center justify-center text-moneygreen-600"><FileSignature className="w-6 h-6" /></div>}
            <div>
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("logo")}</label>
              <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={onLogoFile} data-testid="lh-logo-file"
                className="mt-1 block text-sm text-stone-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer" />
            </div>
          </div>
          <Field label={t("clinicName")}><input required value={lh.clinic_name} onChange={setLhField("clinic_name")} className={inputCls} data-testid="lh-name" /></Field>
          <Field label={t("tagline")}><input value={lh.tagline || ""} onChange={setLhField("tagline")} className={inputCls} data-testid="lh-tagline" /></Field>
          <Field label={t("address")}><input value={lh.address || ""} onChange={setLhField("address")} className={inputCls} data-testid="lh-address" /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("phone")}><input value={lh.phone || ""} onChange={setLhField("phone")} className={inputCls} data-testid="lh-phone" /></Field>
            <Field label={t("email")}><input value={lh.email || ""} onChange={setLhField("email")} className={inputCls} data-testid="lh-email" /></Field>
          </div>
          <Field label={t("whatsapp")}><input value={lh.whatsapp || ""} onChange={setLhField("whatsapp")} className={inputCls} data-testid="lh-whatsapp" placeholder="+1 809 555 0100" /></Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setLhOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-letterhead-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
