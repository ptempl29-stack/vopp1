import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Empty, Card } from "../components/ui-kit";
import { ManagedSelect } from "../components/ManagedSelect";
import { fmtDateTime } from "../lib/date";
import { Plus, Mail, MailOpen, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Messages() {
  const { t } = useLang();
  const { user } = useAuth();
  const sel = useSelection();
  const [messages, setMessages] = useState([]);
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ to_user_id: "", subject: "", body: "" });

  const load = () => api.get("/messages").then((r) => setMessages(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/users").then((r) => setUsers(r.data)).catch(() => {}); }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const send = async (e) => {
    e.preventDefault();
    try { await api.post("/messages", form); toast.success(t("send") + " ✓"); setOpen(false); setForm({ to_user_id: "", subject: "", body: "" }); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const openMsg = async (m) => {
    if (m.to_user_id === user.id && !m.read) { await api.put(`/messages/${m.id}/read`); load(); }
  };

  const removeMsg = async (id) => {
    try { await api.delete(`/messages/${id}`); load(); } catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    try { await bulkDelete("/messages/bulk-delete", [...sel.selected], t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  return (
    <div>
      <PageHeader title={t("messages")} subtitle={t("inbox")}
        action={<Btn onClick={() => setOpen(true)} data-testid="add-message-btn"><Plus className="w-4 h-4" />{t("newMessage")}</Btn>} />

      {messages.length > 0 && (
        <div className="flex items-center gap-3 mb-4">
          <label className="flex items-center gap-1.5 text-sm text-stone-600 cursor-pointer">
            <input type="checkbox" data-testid="select-all-messages"
              checked={sel.count >= messages.length && messages.length > 0}
              onChange={() => sel.toggleAll(messages.map((m) => m.id))}
              className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
            {t("selectAll")}
          </label>
          {sel.count > 0 && (<>
            <span className="text-sm text-stone-500">{sel.count}</span>
            <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-messages"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
            <Btn variant="outline" onClick={sel.clear} data-testid="deselect-messages">{t("deselectAll")}</Btn>
          </>)}
        </div>
      )}

      {messages.length === 0 ? <Card><Empty text={t("noData")} /></Card> : (
        <div className="space-y-3">
          {messages.map((m, i) => {
            const incoming = m.to_user_id === user.id;
            const unread = incoming && !m.read;
            return (
              <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}
                data-testid={`message-${m.id}`}>
                <Card className={`p-4 transition-colors duration-200 ${sel.has(m.id) ? "ring-2 ring-moneygreen-500" : ""} ${unread ? "border-moneygreen-400 bg-moneygreen-50" : ""}`}>
                  <div className="flex items-start gap-3">
                    <input type="checkbox" checked={sel.has(m.id)} onChange={() => sel.toggle(m.id)}
                      data-testid={`select-message-${m.id}`} className="mt-2.5 w-4 h-4 accent-moneygreen-600 cursor-pointer shrink-0" />
                    <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${unread ? "bg-moneygreen-600" : "bg-tan-200"}`}>
                      {unread ? <Mail className="w-4 h-4 text-white" /> : <MailOpen className="w-4 h-4 text-tan-900" />}
                    </div>
                    <div className="min-w-0 flex-1 cursor-pointer" onClick={() => openMsg(m)}>
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-moneygreen-800 text-sm">
                          {incoming ? `${t("from")}: ${m.from_name}` : `${t("to")}: ${m.to_name}`}
                        </p>
                        <span className="text-xs text-stone-400 shrink-0">{fmtDateTime(m.created_at)}</span>
                      </div>
                      {m.subject && <p className="text-sm font-medium text-stone-700">{m.subject}</p>}
                      <p className="text-sm text-stone-500 line-clamp-2">{m.body}</p>
                    </div>
                    <button onClick={() => removeMsg(m.id)} data-testid={`delete-message-${m.id}`}
                      className="text-stone-400 hover:text-destructive transition-colors shrink-0" title={t("delete")}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={t("newMessage")}>
        <form onSubmit={send} className="space-y-4">
          <Field label={t("to")}>
            <ManagedSelect listKey="users" required value={form.to_user_id} onChange={set("to_user_id")} className={inputCls} data-testid="mf-to">
              <option value="">—</option>
              {users.filter((u) => u.id !== user.id).map((u) => (
                <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
              ))}
            </ManagedSelect>
          </Field>
          <Field label={t("subject")}><input value={form.subject} onChange={set("subject")} className={inputCls} data-testid="mf-subject" /></Field>
          <Field label={t("body")}><textarea required value={form.body} onChange={set("body")} rows={4} className={inputCls} data-testid="mf-body" /></Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="send-message-btn">{t("send")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
