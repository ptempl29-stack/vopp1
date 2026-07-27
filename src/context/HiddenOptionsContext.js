import React, { createContext, useContext, useEffect, useState } from "react";
import api from "../lib/api";

const Ctx = createContext(null);

const norm = (list) => String(list || "").replace(/\./g, "_");

export function HiddenOptionsProvider({ children }) {
  const [map, setMap] = useState({});

  useEffect(() => {
    api.get("/hidden-options").then((r) => setMap(r.data || {})).catch((err) => console.error("load hidden options failed", err));
  }, []);

  const isHidden = (list, value) => (map[norm(list)] || []).includes(String(value));

  const hide = async (list, value) => {
    const l = norm(list), v = String(value);
    setMap((m) => ({ ...m, [l]: Array.from(new Set([...(m[l] || []), v])) }));
    try { const r = await api.post("/hidden-options", { list: l, value: v }); setMap(r.data || {}); }
    catch (err) { console.error("hide option failed", err); }
  };

  const restore = async (list, value) => {
    const l = norm(list), v = String(value);
    setMap((m) => ({ ...m, [l]: (m[l] || []).filter((x) => x !== v) }));
    try { const r = await api.post("/hidden-options/restore", { list: l, value: v }); setMap(r.data || {}); }
    catch (err) { console.error("restore option failed", err); }
  };

  return <Ctx.Provider value={{ map, isHidden, hide, restore }}>{children}</Ctx.Provider>;
}

export const useHiddenOptions = () =>
  useContext(Ctx) || { map: {}, isHidden: () => false, hide: () => {}, restore: () => {} };
