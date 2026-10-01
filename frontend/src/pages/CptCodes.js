import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Empty, Card } from "../components/ui-kit";
import { Plus, Pencil, Trash2, Search, Hash } from "lucide-react";
import { toast } from "sonner";

const blank = { code: "", description: "", amount: 0 };

export default function CptCodes() {
  const { t } = useLang();
  const { user } = useAuth();
  const allowed = can(user?.role, "cpt");
  const [codes, setCodes] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState(null);

  const load = () => api.get("/cpt-codes").then((r) => setCodes(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const openNew = () => { setForm(blank); setEditId(null); setOpen(true); };
  const openEdit = (c) => { setForm({ code: c.code, description: c.description, amount: c.amount }); setEditId(c.id); setOpen(true); };

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editId) await api.put(`/cpt-codes/${editId}`, { ...form, amount: parseFloat(form.amount) });
      else await api.post("/cpt-codes", { ...form, amount: parseFloat(form.amount) });
      toast.success(t("save") + " ✓");
      setOpen(false); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const remove = async (id) => {
    try { await api.delete(`/cpt-codes/${id}`); toast.success(t("delete") + " ✓"); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const filtered = codes.filter((c) =>
    !search || c.code.includes(search) || c.description.toLowerCase().includes(search.toLowerCase()));

  return (
    <div>
      <PageHeader title={t("cptCodes")} subtitle={`${codes.length} ${t("cptCodes").toLowerCase()}`}
        action={allowed && <Btn onClick={openNew} data-testid="add-cpt-btn"><Plus className="w-4 h-4" />{t("newCpt")}</Btn>} />

      <div className="relative mb-4 max-w-sm">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("search")}
          data-testid="cpt-search" className={inputCls + " pl-9"} />
      </div>

      <Card className="overflow-hidden">
        {filtered.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("cptCode")}</th>
                  <th className="px-5 py-3">{t("description")}</th>
                  <th className="px-5 py-3 text-right">{t("amount")}</th>
                  {allowed && <th className="px-5 py-3 text-right">{t("actions")}</th>}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c, i) => (
                  <motion.tr key={c.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`cpt-row-${c.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center gap-1.5 font-mono font-semibold text-moneygreen-700">
                        <Hash className="w-3.5 h-3.5 text-moneygreen-400" />{c.code}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-stone-600">{c.description}</td>
                    <td className="px-5 py-3 text-right font-semibold text-moneygreen-800">${Number(c.amount).toFixed(2)}</td>
                    {allowed && (
                      <td className="px-5 py-3">
                        <div className="flex justify-end gap-1">
                          <Btn variant="ghost" onClick={() => openEdit(c)} data-testid={`edit-cpt-${c.id}`} className="!px-2"><Pencil className="w-4 h-4" /></Btn>
                          <Btn variant="ghost" onClick={() => remove(c.id)} data-testid={`delete-cpt-${c.id}`} className="!px-2 !text-destructive"><Trash2 className="w-4 h-4" /></Btn>
                        </div>
                      </td>
                    )}
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title={editId ? t("edit") : t("newCpt")}>
        <form onSubmit={save} className="space-y-4">
          <Field label={t("cptCode")}><input required value={form.code} onChange={set("code")} className={inputCls} data-testid="cf-code" placeholder="99213" /></Field>
          <Field label={t("description")}><input required value={form.description} onChange={set("description")} className={inputCls} data-testid="cf-desc" /></Field>
          <Field label={t("amount")}><input type="number" step="0.01" min="0" required value={form.amount} onChange={set("amount")} className={inputCls} data-testid="cf-amount" /></Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-cpt-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
