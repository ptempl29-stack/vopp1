import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useLang } from "../context/LanguageContext";
import { Btn, Card } from "../components/ui-kit";
import { Sparkles, Plus, Send, Trash2, Loader2, MessageSquareText } from "lucide-react";
import { toast } from "sonner";

export default function AIAssistant() {
  const { t } = useLang();
  const [convos, setConvos] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);
  const sel = useSelection();

  const loadConvos = useCallback(async () => {
    try { setConvos((await api.get("/assistant/conversations")).data); } catch (e) { toast.error(apiErr(e)); }
  }, []);

  useEffect(() => { loadConvos(); }, [loadConvos]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);

  const openConvo = async (id) => {
    setActiveId(id);
    try { setMessages((await api.get(`/assistant/conversations/${id}`)).data.messages || []); }
    catch (e) { toast.error(apiErr(e)); }
  };

  const newChat = async () => {
    try {
      const c = (await api.post("/assistant/conversations")).data;
      setConvos((prev) => [{ id: c.id, title: c.title, message_count: 0 }, ...prev]);
      setActiveId(c.id); setMessages([]);
    } catch (e) { toast.error(apiErr(e)); }
  };

  const deleteConvo = async (id, e) => {
    e.stopPropagation();
    try {
      await api.delete(`/assistant/conversations/${id}`);
      setConvos((prev) => prev.filter((c) => c.id !== id));
      if (activeId === id) { setActiveId(null); setMessages([]); }
    } catch (err) { toast.error(apiErr(err)); }
  };

  const removeSelected = async () => {
    const ids = [...sel.selected];
    try {
      await bulkDelete("/assistant/conversations/bulk-delete", ids, t);
      setConvos((prev) => prev.filter((c) => !sel.has(c.id)));
      if (sel.has(activeId)) { setActiveId(null); setMessages([]); }
      sel.clear();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const send = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    let cid = activeId;
    if (!cid) {
      try {
        const c = (await api.post("/assistant/conversations")).data;
        cid = c.id; setActiveId(cid);
        setConvos((prev) => [{ id: c.id, title: c.title, message_count: 0 }, ...prev]);
      } catch (err) { toast.error(apiErr(err)); return; }
    }
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const r = await api.post(`/assistant/conversations/${cid}/message`, { content: text });
      setMessages((prev) => [...prev, r.data.assistant_message]);
      loadConvos();
    } catch (err) {
      toast.error(apiErr(err));
      setMessages((prev) => prev.slice(0, -1));
      setInput(text);
    } finally { setSending(false); }
  };

  return (
    <div data-testid="assistant-page" className="h-[calc(100vh-8rem)] flex gap-4">
      {/* Conversations sidebar */}
      <div className="hidden md:flex flex-col w-64 shrink-0">
        <Btn onClick={newChat} data-testid="new-chat-btn" className="mb-3 w-full justify-center"><Plus className="w-4 h-4" />{t("newChat")}</Btn>
        {convos.length > 0 && (
          <label className="flex items-center gap-1.5 text-sm text-stone-600 cursor-pointer mb-2 px-1">
            <input type="checkbox" data-testid="select-all-chats"
              checked={sel.count >= convos.length && convos.length > 0}
              onChange={() => sel.toggleAll(convos.map((c) => c.id))}
              className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
            {t("selectAll")}
          </label>
        )}
        {sel.count > 0 && (
          <div className="flex flex-col gap-2 mb-3">
            <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-chats" className="w-full justify-center">
              <Trash2 className="w-4 h-4" />{t("deleteSelected")} ({sel.count})
            </Btn>
            <Btn variant="outline" onClick={sel.clear} data-testid="deselect-chats" className="w-full justify-center">{t("deselectAll")}</Btn>
          </div>
        )}
        <Card className="flex-1 overflow-y-auto custom-scroll p-2">
          {convos.length === 0 ? (
            <p className="text-xs text-stone-400 text-center py-8">{t("noChats")}</p>
          ) : convos.map((c) => (
            <div key={c.id} onClick={() => openConvo(c.id)} data-testid={`convo-${c.id}`}
              className={`group flex items-center gap-2 px-3 py-2.5 rounded-md cursor-pointer transition-colors duration-200 ${activeId === c.id ? "bg-moneygreen-100 text-moneygreen-800" : sel.has(c.id) ? "bg-tan-100" : "hover:bg-tan-100 text-stone-600"}`}>
              <input type="checkbox" checked={sel.has(c.id)} onClick={(e) => e.stopPropagation()} onChange={() => sel.toggle(c.id)}
                data-testid={`select-chat-${c.id}`} className="w-4 h-4 accent-moneygreen-600 cursor-pointer shrink-0" />
              <MessageSquareText className="w-4 h-4 shrink-0 text-moneygreen-500" />
              <span className="text-sm truncate flex-1">{c.title}</span>
              <button onClick={(e) => deleteConvo(c.id, e)} data-testid={`delete-chat-${c.id}`}
                className="opacity-0 group-hover:opacity-100 text-stone-400 hover:text-destructive transition-opacity"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          ))}
        </Card>
      </div>

      {/* Chat panel */}
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-moneygreen-600 flex items-center justify-center"><Sparkles className="w-4 h-4 text-white" /></div>
            <div>
              <p className="font-heading font-bold text-moneygreen-800 leading-tight">{t("aiAssistant")}</p>
              <p className="text-xs text-stone-400">{t("assistantSubtitle")}</p>
            </div>
          </div>
          <Btn variant="outline" onClick={newChat} data-testid="new-chat-btn-mobile" className="md:hidden !px-2"><Plus className="w-4 h-4" /></Btn>
        </div>

        <div className="flex-1 overflow-y-auto custom-scroll p-5 space-y-4">
          {messages.length === 0 && !sending ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-stone-400">
              <Sparkles className="w-10 h-10 mb-3 text-moneygreen-300" />
              <p className="text-sm max-w-xs">{t("assistantEmpty")}</p>
            </div>
          ) : messages.map((m, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              data-testid={`assistant-message-${m.role}`}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${m.role === "user" ? "bg-moneygreen-600 text-white rounded-br-sm" : "bg-tan-100 text-stone-800 rounded-bl-sm"}`}>
                {m.content}
              </div>
            </motion.div>
          ))}
          {sending && (
            <div className="flex justify-start" data-testid="assistant-thinking">
              <div className="px-4 py-2.5 rounded-2xl bg-tan-100 text-stone-500 text-sm flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />{t("thinking")}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={send} className="border-t border-border p-3">
          <div className="flex items-end gap-2">
            <textarea value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(e); } }}
              rows={1} placeholder={t("askAnything")} data-testid="assistant-input"
              className="flex-1 resize-none px-4 py-2.5 rounded-xl bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm max-h-32 custom-scroll" />
            <Btn type="submit" disabled={sending || !input.trim()} data-testid="assistant-send" className="!rounded-xl !px-3.5 !py-2.5">
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Btn>
          </div>
          <p className="text-[11px] text-stone-400 mt-2 text-center">{t("assistantDisclaimer")}</p>
        </form>
      </Card>
    </div>
  );
}
