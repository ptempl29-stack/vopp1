import React, { useCallback, useEffect, useState } from "react";
import DOMPurify from "dompurify";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import {
  Mail, Inbox, SendHorizonal, PenSquare, Trash2, Settings, RefreshCw,
  Paperclip, Plug, ChevronLeft, ChevronRight, CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";

const blankSettings = {
  imap_host: "", imap_port: 993, imap_ssl: true,
  smtp_host: "", smtp_port: 465, smtp_starttls: false,
  email_address: "", password: "", inbox_folder: "INBOX", sent_folder: "Sent", trash_folder: "Trash",
};

const stripName = (from) => {
  if (!from) return "—";
  const m = from.match(/^(.*?)\s*<.*>$/);
  return (m ? m[1].replace(/"/g, "").trim() : from) || from;
};

export default function Mailbox() {
  const { t } = useLang();
  const [configured, setConfigured] = useState(null);
  const [folder, setFolder] = useState("INBOX");
  const [list, setList] = useState({ items: [], total: 0, page: 1, limit: 25 });
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [composeOpen, setComposeOpen] = useState(false);
  const [compose, setCompose] = useState({ to: "", cc: "", subject: "", body_text: "" });
  const [sending, setSending] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState(blankSettings);
  const [savingCfg, setSavingCfg] = useState(false);
  const [testing, setTesting] = useState(false);
  const [page, setPage] = useState(1);

  const loadStatus = useCallback(async () => {
    try {
      const r = await api.get("/mailbox/settings");
      setConfigured(!!r.data.configured);
      if (r.data.configured) setSettings((s) => ({ ...blankSettings, ...r.data, password: "" }));
    } catch (e) { setConfigured(false); }
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/mailbox/messages", { params: { folder, page, limit: 25 } });
      setList(r.data);
    } catch (e) { toast.error(apiErr(e)); }
    finally { setLoading(false); }
  }, [folder, page]);

  useEffect(() => { loadStatus(); }, [loadStatus]);
  useEffect(() => { if (configured) loadList(); }, [configured, loadList]);

  const openMsg = async (uid) => {
    try {
      const r = await api.get(`/mailbox/messages/${uid}`, { params: { folder } });
      setSelected(r.data);
      setList((l) => ({ ...l, items: l.items.map((m) => (m.uid === uid ? { ...m, seen: true } : m)) }));
    } catch (e) { toast.error(apiErr(e)); }
  };

  const del = async (uid) => {
    try {
      await api.delete(`/mailbox/messages/${uid}`, { params: { folder } });
      toast.success(t("deleted"));
      setSelected(null);
      loadList();
    } catch (e) { toast.error(apiErr(e)); }
  };

  const send = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      await api.post("/mailbox/send", {
        to: compose.to.split(",").map((s) => s.trim()).filter(Boolean),
        cc: compose.cc.split(",").map((s) => s.trim()).filter(Boolean),
        subject: compose.subject, body_text: compose.body_text,
      });
      toast.success(t("mailSent"));
      setComposeOpen(false);
      setCompose({ to: "", cc: "", subject: "", body_text: "" });
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSending(false); }
  };

  const saveCfg = async (e) => {
    e.preventDefault();
    setSavingCfg(true);
    try {
      await api.put("/mailbox/settings", settings);
      toast.success(t("saved"));
      setSettingsOpen(false);
      await loadStatus();
      loadList();
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSavingCfg(false); }
  };

  const testCfg = async () => {
    setTesting(true);
    try {
      await api.put("/mailbox/settings", settings);
      await api.post("/mailbox/test");
      toast.success(t("mailboxConnected"));
      await loadStatus();
    } catch (err) { toast.error(apiErr(err)); }
    finally { setTesting(false); }
  };

  const setC = (k) => (e) => setCompose((c) => ({ ...c, [k]: e.target.value }));
  const setS = (k) => (e) => {
    const v = e.target.type === "checkbox" ? e.target.checked : (e.target.type === "number" ? Number(e.target.value) : e.target.value);
    setSettings((s) => ({ ...s, [k]: v }));
  };

  const folders = [
    { key: "INBOX", label: t("inbox"), icon: Inbox },
    { key: settings.sent_folder || "Sent", label: t("sent"), icon: SendHorizonal },
  ];
  const totalPages = Math.max(1, Math.ceil((list.total || 0) / (list.limit || 25)));

  return (
    <div className="space-y-6" data-testid="mailbox-page">
      <PageHeader title={t("mailbox")} subtitle={t("mailboxSubtitle")}
        action={<div className="flex gap-2 flex-wrap">
          <Btn variant="outline" onClick={() => { loadStatus(); loadList(); }} data-testid="mail-refresh"><RefreshCw className="w-4 h-4" />{t("refresh")}</Btn>
          <Btn variant="outline" onClick={() => setSettingsOpen(true)} data-testid="mail-settings-btn"><Settings className="w-4 h-4" />{t("connection")}</Btn>
          <Btn onClick={() => setComposeOpen(true)} disabled={!configured} data-testid="mail-compose-btn"><PenSquare className="w-4 h-4" />{t("compose")}</Btn>
        </div>} />

      {configured === false && (
        <Card className="p-8 text-center">
          <Plug className="w-10 h-10 mx-auto text-moneygreen-500 mb-3" />
          <p className="text-stone-700 font-semibold mb-1">{t("mailboxNotConnected")}</p>
          <p className="text-sm text-stone-500 mb-4">{t("mailboxConnectHint")}</p>
          <Btn onClick={() => setSettingsOpen(true)} data-testid="mail-connect-btn"><Settings className="w-4 h-4" />{t("connectMailbox")}</Btn>
        </Card>
      )}

      {configured && (
        <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-4">
          <div className="space-y-1">
            {folders.map((f) => {
              const Icon = f.icon;
              const active = folder === f.key;
              return (
                <button key={f.key} onClick={() => { setFolder(f.key); setPage(1); setSelected(null); }}
                  data-testid={`mail-folder-${f.label.toLowerCase()}`}
                  className={`w-full flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-colors duration-200 ${active ? "bg-moneygreen-700 text-white" : "text-stone-600 hover:bg-tan-50"}`}>
                  <Icon className="w-4 h-4" />{f.label}
                </button>
              );
            })}
          </div>

          <Card className="overflow-hidden">
            {loading ? (
              <div className="p-10 text-center text-stone-400 text-sm">{t("loading")}…</div>
            ) : list.items.length === 0 ? (
              <Empty icon={Mail} title={t("noEmails")} />
            ) : (
              <div className="divide-y divide-border">
                {list.items.map((m, i) => (
                  <motion.button key={m.uid} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.015 }}
                    onClick={() => openMsg(m.uid)} data-testid={`mail-row-${m.uid}`}
                    className={`w-full text-left px-5 py-3 hover:bg-tan-50 transition-colors duration-150 flex items-center gap-3 ${m.seen ? "" : "bg-moneygreen-50/60"}`}>
                    {!m.seen && <span className="w-2 h-2 rounded-full bg-moneygreen-600 shrink-0" />}
                    <span className={`w-44 truncate text-sm shrink-0 ${m.seen ? "text-stone-600" : "text-stone-900 font-semibold"}`}>
                      {folder === "INBOX" ? stripName(m.from_) : stripName(m.to)}
                    </span>
                    <span className={`flex-1 truncate text-sm ${m.seen ? "text-stone-500" : "text-stone-800 font-medium"}`}>
                      {m.subject || `(${t("noSubject")})`}
                    </span>
                    <span className="text-xs text-stone-400 shrink-0 hidden sm:block">{(m.date || "").replace(/\s*\(.*\)$/, "").slice(0, 22)}</span>
                  </motion.button>
                ))}
              </div>
            )}
            <div className="flex items-center justify-between px-5 py-3 border-t border-border bg-tan-50/40">
              <span className="text-xs text-stone-500">{list.total} {t("messagesTotal")}</span>
              <div className="flex items-center gap-2">
                <Btn variant="ghost" className="!px-2" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} data-testid="mail-prev"><ChevronLeft className="w-4 h-4" /></Btn>
                <span className="text-xs text-stone-500">{page} / {totalPages}</span>
                <Btn variant="ghost" className="!px-2" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} data-testid="mail-next"><ChevronRight className="w-4 h-4" /></Btn>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* View message */}
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.subject || t("noSubject")} wide>
        {selected && (
          <div className="space-y-4">
            <div className="text-sm text-stone-600 space-y-0.5 pb-3 border-b border-border">
              <div><span className="font-semibold text-stone-500">{t("from")}:</span> {selected.from_}</div>
              <div><span className="font-semibold text-stone-500">{t("to")}:</span> {selected.to}</div>
              {selected.cc && <div><span className="font-semibold text-stone-500">Cc:</span> {selected.cc}</div>}
              <div className="text-xs text-stone-400">{selected.date}</div>
            </div>
            {selected.body_html
              ? <div className="prose prose-sm max-w-none text-stone-700 max-h-[50vh] overflow-y-auto" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(selected.body_html, { ADD_ATTR: ["target"] }) }} />
              : <pre className="whitespace-pre-wrap text-sm text-stone-700 font-sans max-h-[50vh] overflow-y-auto">{selected.body_text}</pre>}
            {selected.attachments?.length > 0 && (
              <div className="pt-3 border-t border-border">
                <p className="text-xs font-semibold text-stone-500 mb-2 flex items-center gap-1"><Paperclip className="w-3.5 h-3.5" />{t("attachments")}</p>
                <div className="flex flex-wrap gap-2">
                  {selected.attachments.map((a, i) => (
                    <a key={i} href={`data:${a.content_type};base64,${a.data_b64}`} download={a.filename}
                      data-testid={`mail-attach-${i}`}
                      className="inline-flex items-center gap-1.5 text-xs bg-tan-50 border border-border rounded-lg px-3 py-1.5 text-moneygreen-800 hover:bg-tan-100">
                      <Paperclip className="w-3 h-3" />{a.filename}
                    </a>
                  ))}
                </div>
              </div>
            )}
            <div className="flex justify-between pt-2">
              <Btn variant="outline" onClick={() => { setCompose({ to: selected.from_, cc: "", subject: `Re: ${selected.subject || ""}`, body_text: `\n\n----------\n${selected.body_text || ""}` }); setSelected(null); setComposeOpen(true); }} data-testid="mail-reply"><SendHorizonal className="w-4 h-4" />{t("reply")}</Btn>
              <Btn variant="ghost" className="!text-destructive" onClick={() => del(selected.uid)} data-testid="mail-delete"><Trash2 className="w-4 h-4" />{t("delete")}</Btn>
            </div>
          </div>
        )}
      </Modal>

      {/* Compose */}
      <Modal open={composeOpen} onClose={() => setComposeOpen(false)} title={t("newMessage")} wide>
        <form onSubmit={send} className="space-y-3">
          <Field label={t("to")}><input required value={compose.to} onChange={setC("to")} className={inputCls} placeholder="patient@email.com, other@email.com" data-testid="mail-to" /></Field>
          <Field label="Cc"><input value={compose.cc} onChange={setC("cc")} className={inputCls} data-testid="mail-cc" /></Field>
          <Field label={t("subject")}><input value={compose.subject} onChange={setC("subject")} className={inputCls} data-testid="mail-subject" /></Field>
          <Field label={t("body")}><textarea rows={10} value={compose.body_text} onChange={setC("body_text")} className={inputCls} data-testid="mail-body" /></Field>
          <div className="flex justify-end gap-2 pt-1">
            <Btn variant="outline" type="button" onClick={() => setComposeOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" disabled={sending || !compose.to} data-testid="mail-send"><SendHorizonal className="w-4 h-4" />{t("send")}</Btn>
          </div>
        </form>
      </Modal>

      {/* Connection settings */}
      <Modal open={settingsOpen} onClose={() => setSettingsOpen(false)} title={t("mailboxConnection")} wide>
        <form onSubmit={saveCfg} className="space-y-4">
          <p className="text-sm text-stone-500">{t("mailboxConnectionHint")}</p>
          <Field label={t("emailAddress")}><input required type="email" value={settings.email_address} onChange={setS("email_address")} className={inputCls} placeholder="forms@veteransofpuertoplata.com" data-testid="cfg-email" /></Field>
          <Field label={t("mailboxPassword")}><input type="password" value={settings.password} onChange={setS("password")} className={inputCls} placeholder={configured ? t("passwordUnchanged") : "app password"} data-testid="cfg-password" /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("imapHost")}><input required value={settings.imap_host} onChange={setS("imap_host")} className={inputCls} placeholder="imap.gmail.com" data-testid="cfg-imap-host" /></Field>
            <Field label={t("imapPort")}><input type="number" value={settings.imap_port} onChange={setS("imap_port")} className={inputCls} data-testid="cfg-imap-port" /></Field>
            <Field label={t("smtpHost")}><input required value={settings.smtp_host} onChange={setS("smtp_host")} className={inputCls} placeholder="smtp.gmail.com" data-testid="cfg-smtp-host" /></Field>
            <Field label={t("smtpPort")}><input type="number" value={settings.smtp_port} onChange={setS("smtp_port")} className={inputCls} data-testid="cfg-smtp-port" /></Field>
            <Field label={t("sentFolder")}><input value={settings.sent_folder} onChange={setS("sent_folder")} className={inputCls} data-testid="cfg-sent" /></Field>
            <Field label={t("trashFolder")}><input value={settings.trash_folder} onChange={setS("trash_folder")} className={inputCls} data-testid="cfg-trash" /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-stone-600">
            <input type="checkbox" checked={settings.smtp_starttls} onChange={setS("smtp_starttls")} data-testid="cfg-starttls" />
            {t("smtpStarttls")}
          </label>
          <div className="flex justify-between gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={testCfg} disabled={testing} data-testid="cfg-test"><CheckCircle2 className="w-4 h-4" />{t("testConnection")}</Btn>
            <div className="flex gap-2">
              <Btn variant="outline" type="button" onClick={() => setSettingsOpen(false)}>{t("cancel")}</Btn>
              <Btn type="submit" disabled={savingCfg} data-testid="cfg-save">{t("save")}</Btn>
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
}
