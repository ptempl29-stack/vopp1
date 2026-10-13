import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { ManagedSelect } from "../components/ManagedSelect";
import { fmtDateTime } from "../lib/date";
import { Plus, Mail, MailOpen, Trash2, Paperclip, Download, Check, CheckCheck } from "lucide-react";
import { toast } from "sonner";

const otherParty = (m, userId) => (m.to_user_id === userId
  ? { id: m.from_user_id, name: m.from_name }
  : { id: m.to_user_id, name: m.to_name });

export default function Messages() {
  const { t } = useLang();
  const { user } = useAuth();
  const sel = useSelection();
  const [messages, setMessages] = useState([]);
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ to_user_id: "", subject: "", body: "", file: null });
  const [sending, setSending] = useState(false);
  const [activeThread, setActiveThread] = useState(null);
  const [replyBody, setReplyBody] = useState("");
  const [replyFile, setReplyFile] = useState(null);
  const [replying, setReplying] = useState(false);
  const fileRef = useRef(null);
  const replyFileRef = useRef(null);

  const load = () => api.get("/messages").then((r) => setMessages(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/users").then((r) => setUsers(r.data)).catch(() => {}); }, []);

  // Conversations: group every message into its thread (older messages
  // created before threading existed fall back to their own id, so they
  // still show up as a single-message conversation).
  const threads = useMemo(() => {
    const byId = new Map();
    for (const m of messages) {
      const key = m.thread_id || m.id;
      if (!byId.has(key)) byId.set(key, []);
      byId.get(key).push(m);
    }
    const list = [...byId.entries()].map(([id, msgs]) => {
      const sorted = [...msgs].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      const last = sorted[sorted.length - 1];
      const unread = sorted.filter((m) => m.to_user_id === user.id && !m.read).length;
      const other = otherParty(last, user.id);
      return { id, msgs: sorted, last, unread, other, subject: sorted[0].subject };
    });
    list.sort((a, b) => new Date(b.last.created_at) - new Date(a.last.created_at));
    return list;
  }, [messages, user.id]);

  const totalUnread = useMemo(() => threads.reduce((s, th) => s + th.unread, 0), [threads]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const send = async (e) => {
    e.preventDefault();
    if (!form.to_user_id) { toast.error(t("to")); return; }
    setSending(true);
    try {
      const fd = new FormData();
      fd.append("to_user_id", form.to_user_id);
      fd.append("subject", form.subject || "");
      fd.append("body", form.body);
      if (form.file) fd.append("file", form.file);
      await api.post("/messages", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(t("send") + " ✓");
      setOpen(false); setForm({ to_user_id: "", subject: "", body: "", file: null });
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSending(false); }
  };

  const openThread = async (th) => {
    setActiveThread(th); setReplying(false); setReplyBody(""); setReplyFile(null);
    if (th.unread > 0) {
      await api.put(`/messages/thread/${th.id}/read`).catch(() => {});
      load();
    }
  };

  const sendReply = async (e) => {
    e.preventDefault();
    if (!activeThread) return;
    const other = activeThread.other;
    const subj = (activeThread.subject || "").toLowerCase().startsWith("re:")
      ? activeThread.subject : `Re: ${activeThread.subject || ""}`;
    try {
      const fd = new FormData();
      fd.append("to_user_id", other.id);
      fd.append("subject", subj);
      fd.append("body", replyBody);
      fd.append("thread_id", activeThread.id);
      if (replyFile) fd.append("file", replyFile);
      await api.post("/messages", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(t("send") + " ✓");
      setReplying(false); setReplyBody(""); setReplyFile(null);
      if (replyFileRef.current) replyFileRef.current.value = "";
      const r = await api.get("/messages");
      setMessages(r.data);
      const key = activeThread.id;
      const msgs = r.data.filter((m) => (m.thread_id || m.id) === key)
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      setActiveThread((th) => (th ? { ...th, msgs } : th));
    } catch (err) { toast.error(apiErr(err)); }
  };

  const downloadAttachment = async (m) => {
    try {
      const res = await api.get(`/messages/${m.id}/attachment`, { responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = m.attachment?.filename || "attachment";
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { toast.error(apiErr(err)); }
  };

  const removeThread = async (th) => {
    try {
      await bulkDelete("/messages/bulk-delete", th.msgs.map((m) => m.id), t);
      if (activeThread?.id === th.id) setActiveThread(null);
      load();
    } catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    const ids = threads.filter((th) => sel.has(th.id)).flatMap((th) => th.msgs.map((m) => m.id));
    try { await bulkDelete("/messages/bulk-delete", ids, t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  return (
    <div>
      <PageHeader title={t("messages")}
        subtitle={totalUnread > 0 ? `${t("inbox")} · ${totalUnread} ${t("unread")}` : t("inbox")}
        action={<Btn onClick={() => setOpen(true)} data-testid="add-message-btn"><Plus className="w-4 h-4" />{t("newMessage")}</Btn>} />

      {threads.length > 0 && (
        <div className="flex items-center gap-3 mb-4">
          <label className="flex items-center gap-1.5 text-sm text-stone-600 cursor-pointer">
            <input type="checkbox" data-testid="select-all-messages"
              checked={sel.count >= threads.length && threads.length > 0}
              onChange={() => sel.toggleAll(threads.map((th) => th.id))}
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

      {threads.length === 0 ? <Card><Empty text={t("noData")} /></Card> : (
        <div className="space-y-3">
          {threads.map((th, i) => (
            <motion.div key={th.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}
              data-testid={`message-thread-${th.id}`}>
              <Card className={`p-4 transition-colors duration-200 ${sel.has(th.id) ? "ring-2 ring-moneygreen-500" : ""} ${th.unread > 0 ? "border-moneygreen-400 bg-moneygreen-50" : ""}`}>
                <div className="flex items-start gap-3">
                  <input type="checkbox" checked={sel.has(th.id)} onChange={() => sel.toggle(th.id)}
                    data-testid={`select-message-${th.id}`} className="mt-2.5 w-4 h-4 accent-moneygreen-600 cursor-pointer shrink-0" />
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${th.unread > 0 ? "bg-moneygreen-600" : "bg-tan-200"}`}>
                    {th.unread > 0 ? <Mail className="w-4 h-4 text-white" /> : <MailOpen className="w-4 h-4 text-tan-900" />}
                  </div>
                  <div className="min-w-0 flex-1 cursor-pointer" onClick={() => openThread(th)}>
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold text-moneygreen-800 text-sm flex items-center gap-2">
                        {th.other.name}
                        {th.msgs.length > 1 && <Badge tone="tan">{th.msgs.length}</Badge>}
                        {th.unread > 0 && <Badge tone="green">{th.unread} {t("unread")}</Badge>}
                      </p>
                      <span className="text-xs text-stone-400 shrink-0">{fmtDateTime(th.last.created_at)}</span>
                    </div>
                    {th.subject && <p className="text-sm font-medium text-stone-700">{th.subject}</p>}
                    <p className="text-sm text-stone-500 line-clamp-2">
                      {th.last.from_user_id === user.id ? `${t("you")}: ` : ""}{th.last.body}
                      {th.last.attachment && <Paperclip className="inline w-3.5 h-3.5 ml-1 text-stone-400" />}
                    </p>
                  </div>
                  <button onClick={() => removeThread(th)} data-testid={`delete-message-${th.id}`}
                    className="text-stone-400 hover:text-destructive transition-colors shrink-0" title={t("delete")}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      {/* New message */}
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
          <Field label={t("attachment")}>
            <input ref={fileRef} type="file" data-testid="mf-attachment"
              onChange={(e) => setForm({ ...form, file: e.target.files[0] || null })}
              className="block w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer" />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" disabled={sending} data-testid="send-message-btn">{t("send")}</Btn>
          </div>
        </form>
      </Modal>

      {/* Conversation thread */}
      <Modal open={!!activeThread} onClose={() => setActiveThread(null)} title={activeThread ? `${activeThread.other.name}${activeThread.subject ? " · " + activeThread.subject : ""}` : t("messages")} wide>
        {activeThread && (
          <div className="space-y-4" data-testid="view-message-modal">
            <div className="space-y-3 max-h-[50vh] overflow-y-auto custom-scroll pr-1">
              {activeThread.msgs.map((m) => {
                const mine = m.from_user_id === user.id;
                return (
                  <div key={m.id} data-testid={`thread-message-${m.id}`}
                    className={`p-3 rounded-lg border max-w-[85%] ${mine ? "ml-auto bg-moneygreen-50 border-moneygreen-200" : "bg-white border-border"}`}>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-xs font-semibold text-moneygreen-800">{mine ? t("you") : m.from_name}</span>
                      <span className="text-xs text-stone-400">{fmtDateTime(m.created_at)}</span>
                    </div>
                    <p className="text-sm text-stone-700 whitespace-pre-wrap">{m.body}</p>
                    {m.attachment && (
                      <button type="button" onClick={() => downloadAttachment(m)} data-testid={`thread-attachment-${m.id}`}
                        className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-moneygreen-700 hover:text-moneygreen-900">
                        <Paperclip className="w-3.5 h-3.5" />{m.attachment.filename}<Download className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {mine && (
                      <p className="mt-1 text-[11px] text-stone-400 flex items-center gap-1" data-testid={`thread-read-status-${m.id}`}>
                        {m.read ? <><CheckCheck className="w-3.5 h-3.5 text-moneygreen-600" />{t("readStatus")}</> : <><Check className="w-3.5 h-3.5" />{t("sentStatus")}</>}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            {!replying ? (
              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Btn variant="outline" onClick={() => setActiveThread(null)}>{t("cancel")}</Btn>
                <Btn onClick={() => setReplying(true)} data-testid="reply-message-btn">{t("reply")}</Btn>
              </div>
            ) : (
              <form onSubmit={sendReply} className="space-y-3 border-t border-border pt-4">
                <Field label={t("body")}>
                  <textarea required autoFocus value={replyBody} onChange={(e) => setReplyBody(e.target.value)} rows={3} className={inputCls} data-testid="reply-body" />
                </Field>
                <Field label={t("attachment")}>
                  <input ref={replyFileRef} type="file" data-testid="reply-attachment"
                    onChange={(e) => setReplyFile(e.target.files[0] || null)}
                    className="block w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer" />
                </Field>
                <div className="flex justify-end gap-2">
                  <Btn variant="outline" type="button" onClick={() => setReplying(false)}>{t("cancel")}</Btn>
                  <Btn type="submit" data-testid="send-reply-btn">{t("send")}</Btn>
                </div>
              </form>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
