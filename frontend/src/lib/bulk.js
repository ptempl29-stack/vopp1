import { useState } from "react";
import api from "./api";
import { toast } from "sonner";

export function useSelection() {
  const [selected, setSelected] = useState(() => new Set());
  const toggle = (id) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const toggleAll = (ids) =>
    setSelected((s) => (s.size >= ids.length && ids.length > 0 ? new Set() : new Set(ids)));
  const clear = () => setSelected(new Set());
  return { selected, toggle, toggleAll, clear, has: (id) => selected.has(id), count: selected.size };
}

export async function bulkDelete(endpoint, ids, t) {
  const r = await api.post(endpoint, { ids });
  const { deleted, skipped } = r.data;
  if (skipped > 0) toast.info(`${deleted} ${t("deleted")} · ${t("onlyOwnDeleted")}`);
  else toast.success(`${deleted} ${t("deleted")} ✓`);
  return r.data;
}
