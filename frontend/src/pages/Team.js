import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { roleLabel } from "../lib/perms";
import { UserPlus, Trash2, ShieldCheck, Pencil, FileSignature, Mail, MailCheck, Copy, Link2, Send, Ban, RotateCcw, Users, KeyRound, LogOut } from "lucide-react";
import { toast } from "sonner";

const ALL_TABS = ["dashboard", "patients", "appointments", "telehealth", "notes",
  "invoices", "cpt", "reports", "forms", "folders", "messages", "team", "audit", "claims", "assistant"];

const roleColors = {
  doctor: "green", nurse: "green", psychologist: "green",
  receptionist: "tan", biller: "gray", admin: "green",
};

export default function Team() {
  const { t } = useLang();
  const { user: me } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [defaults, setDefaults] = useState({});
  const [editUser, setEditUser] = useState(null);
  const [editTabs, setEditTabs] = useState([]);
  const [infoUser, setInfoUser] = useState(null);
  const [infoForm, setInfoForm] = useState({ name: "", email: "", role: "", password: "" });
  const [pwUser, setPwUser] = useState(null);
  const [pwForm, setPwForm] = useState({ password: "", require_change: true });
  const [lhOpen, setLhOpen] = useState(false);
  const [lh, setLh] = useState({ clinic_name: "", tagline: "", address: "", phone: "", email: "", logo: "" });
  const [invites, setInvites] = useState([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "receptionist", allowed_tabs: [] });
  const [createdLink, setCreatedLink] = useState("");
  const [roleTpl, setRoleTpl] = useState(null);
  const [testOpen, setTestOpen] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [testBusy, setTestBusy] = useState(false);

  const sendTest = async (e) => {
    e.preventDefault();
    setTestBusy(true);
    try {
      const r = await api.post("/settings/test-email", { to: testEmail });
      toast.success(`${t("testEmailSent")} ${r.data.sender}`);
      setTestOpen(false);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setTestBusy(false); }
  };

  const loadMeta = () => api.get("/meta/tabs").then((r) => { setRoles(r.data.roles); setDefaults(r.data.defaults); }).catch(() => {});

  const toggleActive = async (u) => {
    const next = u.active === false;
    if (!next && !window.confirm(t("confirmSuspend"))) return;
    try {
      await api.put(`/users/${u.id}/active`, { active: next });
      toast.success(next ? t("accessRestored") : t("accessSuspended"));
      load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const openRoleTpl = (role) => setRoleTpl({ role, allowed_tabs: [...(defaults[role] || [])], apply_to_existing: false });
  const toggleRoleTplTab = (tab) => setRoleTpl((s) => ({
    ...s, allowed_tabs: s.allowed_tabs.includes(tab) ? s.allowed_tabs.filter((x) => x !== tab) : [...s.allowed_tabs, tab],
  }));
  const saveRoleTpl = async () => {
    try {
      await api.put(`/role-templates/${roleTpl.role}`, { allowed_tabs: roleTpl.allowed_tabs, apply_to_existing: roleTpl.apply_to_existing });
      toast.success(t("roleTemplateSaved"));
      setRoleTpl(null); loadMeta(); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

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
    loadMeta();
  }, []);

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

  const openReset = (u) => { setPwUser(u); setPwForm({ password: "", require_change: true }); };
  const doReset = async (e) => {
    e.preventDefault();
    try {
      await api.put(`/users/${pwUser.id}/password`, { password: pwForm.password, require_change: pwForm.require_change });
      toast.success(t("passwordResetDone"));
      setPwUser(null);
    } catch (err) { toast.error(apiErr(err)); }
  };
  const forceLogout = async (u) => {
    if (!window.confirm(t("confirmForceLogout"))) return;
    try { await api.post(`/users/${u.id}/logout`); toast.success(t("forceLogoutDone")); }
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

  return (
    <div>
      <PageHeader title={t("settings")} subtitle={t("settingsSubtitle")}
        action={<div className="flex gap-2 flex-wrap">
          <Btn variant="outline" onClick={openLetterhead} data-testid="edit-letterhead-btn"><FileSignature className="w-4 h-4" />{t("letterhead")}</Btn>
          {me?.role === "admin" && <Btn variant="outline" onClick={() => { setTestEmail(me?.email || ""); setTestOpen(true); }} data-testid="test-email-btn"><MailCheck className="w-4 h-4" />{t("sendTestEmail")}</Btn>}
          <Btn variant="outline" onClick={openInvite} data-testid="invite-staff-btn"><Mail className="w-4 h-4" />{t("inviteStaff")}</Btn>
          <Btn onClick={() => navigate("/enroll")} data-testid="add-user-btn"><UserPlus className="w-4 h-4" />{t("enrollStaff")}</Btn>
        </div>} />

      <h3 className="font-heading text-lg font-bold text-moneygreen-800 mb-3">{t("staffMembers")}</h3>

      {users.filter((u) => u.role === "admin").length < 2 && (
        <div data-testid="lockout-banner" className="mb-4 flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
          <div className="flex items-start gap-3 flex-1">
            <ShieldCheck className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-amber-800 text-sm">{t("lockoutTitle")}</p>
              <p className="text-sm text-amber-700">{t("lockoutMsg")}</p>
            </div>
          </div>
          <Btn onClick={() => navigate("/enroll")} data-testid="enroll-backup-admin-btn" className="shrink-0"><UserPlus className="w-4 h-4" />{t("enrollBackupAdmin")}</Btn>
        </div>
      )}
      <Card className="overflow-hidden">
        {users.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("name")}</th>
                  <th className="px-5 py-3">{t("role")}</th>
                  <th className="px-5 py-3">{t("status")}</th>
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
                    <td className="px-5 py-3"><Badge tone={roleColors[u.role] || "gray"}>{roleLabel(u.role)}</Badge></td>
                    <td className="px-5 py-3">
                      <Badge tone={u.active === false ? "gray" : "green"} data-testid={`user-status-${u.id}`}>
                        {u.active === false ? t("suspended") : t("active")}
                      </Badge>
                    </td>
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
                        {u.id !== me.id && (
                          <>
                            <Btn variant="ghost" onClick={() => openReset(u)} data-testid={`reset-pw-${u.id}`} className="!px-2 !text-moneygreen-700" title={t("resetPassword")}>
                              <KeyRound className="w-4 h-4" />
                            </Btn>
                            <Btn variant="ghost" onClick={() => forceLogout(u)} data-testid={`force-logout-${u.id}`} className="!px-2 !text-stone-500" title={t("forceLogout")}>
                              <LogOut className="w-4 h-4" />
                            </Btn>
                          </>
                        )}
                        {u.id !== me.id && u.role !== "admin" && (
                          <Btn variant="ghost" onClick={() => toggleActive(u)} data-testid={`toggle-active-${u.id}`}
                            className={`!px-2 ${u.active === false ? "!text-moneygreen-600" : "!text-amber-600"}`}
                            title={u.active === false ? t("restore") : t("suspend")}>
                            {u.active === false ? <RotateCcw className="w-4 h-4" /> : <Ban className="w-4 h-4" />}
                          </Btn>
                        )}
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
                      <td className="px-5 py-3"><Badge tone="tan">{roleLabel(iv.role)}</Badge></td>
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

      <div className="mt-8">
        <h3 className="font-heading text-lg font-bold text-moneygreen-800 mb-1">{t("roleAccess")}</h3>
        <p className="text-sm text-stone-400 mb-3">{t("roleAccessSubtitle")}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="role-templates">
          {(roles.length ? roles : ["doctor", "nurse", "psychologist", "receptionist", "biller"]).filter((r) => r !== "admin").map((role) => (
            <Card key={role} className="p-4 flex flex-col" data-testid={`role-card-${role}`}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-md bg-moneygreen-100 flex items-center justify-center text-moneygreen-600"><Users className="w-4 h-4" /></div>
                <span className="font-heading font-bold capitalize text-moneygreen-800">{roleLabel(role)}</span>
                <span className="ml-auto text-xs text-stone-400">{(defaults[role] || []).length} tabs</span>
              </div>
              <div className="flex flex-wrap gap-1.5 mb-3 flex-1">
                {(defaults[role] || []).map((tb) => (
                  <span key={tb} className="text-[11px] px-2 py-0.5 rounded-full bg-tan-100 text-stone-600 capitalize">{tb}</span>
                ))}
              </div>
              <Btn variant="outline" onClick={() => openRoleTpl(role)} data-testid={`edit-role-${role}`} className="w-full justify-center">
                <ShieldCheck className="w-4 h-4" />{t("editRoleTemplate")}
              </Btn>
            </Card>
          ))}
        </div>
      </div>

      <Modal open={!!roleTpl} onClose={() => setRoleTpl(null)} title={roleTpl ? `${t("editRoleTemplate")} — ${roleLabel(roleTpl.role)}` : ""}>
        {roleTpl && (
          <div>
            <div className="grid grid-cols-2 gap-2" data-testid="role-tabs-checklist">
              {ALL_TABS.map((tab) => (
                <label key={tab} className="flex items-center gap-2 px-3 py-2 rounded-md border border-border cursor-pointer hover:bg-tan-50 transition-colors duration-200">
                  <input type="checkbox" checked={roleTpl.allowed_tabs.includes(tab)} onChange={() => toggleRoleTplTab(tab)}
                    data-testid={`role-tab-${tab}`} className="w-4 h-4 accent-moneygreen-600" />
                  <span className="text-sm capitalize text-moneygreen-800">{tab}</span>
                </label>
              ))}
            </div>
            <label className="flex items-center gap-2 mt-4 cursor-pointer">
              <input type="checkbox" checked={roleTpl.apply_to_existing} onChange={(e) => setRoleTpl({ ...roleTpl, apply_to_existing: e.target.checked })}
                data-testid="apply-to-existing" className="w-4 h-4 accent-moneygreen-600" />
              <span className="text-sm text-stone-600">{t("applyToExisting")}</span>
            </label>
            <div className="flex justify-end gap-2 pt-4">
              <Btn variant="outline" type="button" onClick={() => setRoleTpl(null)}>{t("cancel")}</Btn>
              <Btn onClick={saveRoleTpl} data-testid="save-role-template-btn">{t("save")}</Btn>
            </div>
          </div>
        )}
      </Modal>

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
                {(roles.length ? roles : ["doctor", "nurse", "psychologist", "receptionist", "biller"]).filter((r) => r !== "admin").map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
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

      <Modal open={!!pwUser} onClose={() => setPwUser(null)} title={pwUser ? `${t("resetPassword")} — ${pwUser.name}` : ""}>
        {pwUser && (
          <form onSubmit={doReset} className="space-y-4">
            <Field label={t("newPassword")}>
              <input type="password" required minLength={6} value={pwForm.password} onChange={(e) => setPwForm({ ...pwForm, password: e.target.value })} className={inputCls} data-testid="reset-pw-input" placeholder="••••••" />
            </Field>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={pwForm.require_change} onChange={(e) => setPwForm({ ...pwForm, require_change: e.target.checked })}
                data-testid="reset-require-change" className="w-4 h-4 accent-moneygreen-600" />
              <span className="text-sm text-stone-600">{t("requirePwChange")}</span>
            </label>
            <p className="text-xs text-stone-400">{t("confirmForceLogout")}</p>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setPwUser(null)}>{t("cancel")}</Btn>
              <Btn type="submit" data-testid="save-reset-pw-btn"><KeyRound className="w-4 h-4" />{t("setNewPassword")}</Btn>
            </div>
          </form>
        )}
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
                {(roles.length ? roles : ["doctor", "nurse", "psychologist", "receptionist", "biller", "admin"]).map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
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
          <Field label={t("usdToDop")}><input type="number" step="0.01" min="1" value={lh.usd_to_dop ?? 60} onChange={setLhField("usd_to_dop")} className={inputCls} data-testid="lh-usd-dop" /></Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setLhOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-letterhead-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
      <Modal open={testOpen} onClose={() => setTestOpen(false)} title={t("sendTestEmail")}>
        <form onSubmit={sendTest} className="space-y-4">
          <p className="text-sm text-stone-500">{t("testEmailHint")}</p>
          <Field label={t("recipientEmail")}>
            <input type="email" required value={testEmail} onChange={(e) => setTestEmail(e.target.value)} className={inputCls} data-testid="test-email-input" placeholder="you@email.com" />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setTestOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" disabled={testBusy || !testEmail} data-testid="send-test-email-btn"><Send className="w-4 h-4" />{t("sendTestEmail")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
