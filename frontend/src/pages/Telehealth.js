import React, { useEffect, useMemo, useState } from "react";
import api, { apiErr } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Btn, Card, inputCls } from "../components/ui-kit";
import { Video, Calendar, Save, Link2, Mail, ShieldCheck, ExternalLink, Loader2, Copy, LayoutGrid, List } from "lucide-react";
import { toast } from "sonner";

export default function Telehealth() {
  const { t } = useLang();
  const { user, refreshUser } = useAuth();
  const [appts, setAppts] = useState([]);
  const [room, setRoom] = useState(user?.doxy_room || "");
  const [savingRoom, setSavingRoom] = useState(false);
  const [inviting, setInviting] = useState(null);
  const [viewMode, setViewMode] = useState("cards");

  useEffect(() => { setRoom(user?.doxy_room || ""); }, [user]);
  useEffect(() => { api.get("/appointments").then((r) => setAppts(r.data)).catch(() => {}); }, []);

  const activeAppts = useMemo(() => appts.filter((a) => a.status !== "cancelled"), [appts]);
  const hasRoom = !!user?.doxy_room;

  const saveRoom = async () => {
    setSavingRoom(true);
    try {
      const r = await api.put("/telehealth/my-room", { room });
      await refreshUser();
      setRoom(r.data.doxy_room);
      toast.success(t("roomSaved"));
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSavingRoom(false); }
  };

  const openMyRoom = () => window.open(`https://doxy.me/${encodeURIComponent(user.doxy_room)}`, "_blank", "noopener,noreferrer");

  const invite = async (a, sendEmail) => {
    setInviting(a.id + (sendEmail ? "-email" : ""));
    try {
      const r = await api.post("/telehealth/doxy-invite", {
        patient_name: a.patient_name, patient_id: a.patient_id, send_email: false,
      });
      await navigator.clipboard.writeText(r.data.join_url).catch(() => {});
      toast.success(t("linkCopied"));
    } catch (err) { toast.error(apiErr(err)); }
    finally { setInviting(null); }
  };

  return (
    <div data-testid="telehealth-page">
      <PageHeader title={t("telehealth")} subtitle={t("roomReady")}
        action={
          <div className="flex items-center gap-2">
            {hasRoom && (
              <div className="flex rounded-md border border-border overflow-hidden" data-testid="tele-view-toggle">
                <button onClick={() => setViewMode("cards")} data-testid="tele-view-cards" title={t("cardView")}
                  className={`px-2.5 py-1.5 transition-colors ${viewMode === "cards" ? "bg-moneygreen-600 text-white" : "bg-white text-moneygreen-700 hover:bg-moneygreen-50"}`}>
                  <LayoutGrid className="w-4 h-4" />
                </button>
                <button onClick={() => setViewMode("list")} data-testid="tele-view-list" title={t("listView")}
                  className={`px-2.5 py-1.5 transition-colors ${viewMode === "list" ? "bg-moneygreen-600 text-white" : "bg-white text-moneygreen-700 hover:bg-moneygreen-50"}`}>
                  <List className="w-4 h-4" />
                </button>
              </div>
            )}
            {hasRoom && <Btn onClick={openMyRoom} data-testid="open-room-btn"><Video className="w-4 h-4" />{t("openMyRoom")}</Btn>}
          </div>
        } />

      <Card className="p-5 mb-6 bg-moneygreen-50 border-moneygreen-100">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-11 h-11 rounded-md bg-moneygreen-600 flex items-center justify-center shrink-0">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="font-heading font-bold text-moneygreen-800">{t("myDoxyRoom")}</p>
            <p className="text-sm text-stone-500">{t("doxyHint")}</p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <div className="flex items-center flex-1 rounded-md border border-border bg-white overflow-hidden">
            <span className="px-3 py-2 text-sm text-stone-400 border-r border-border select-none">doxy.me/</span>
            <input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="drmarte"
              className="flex-1 px-3 py-2 text-sm focus:outline-none" data-testid="doxy-room-input" />
          </div>
          <Btn onClick={saveRoom} disabled={savingRoom} data-testid="save-room-btn">
            {savingRoom ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{t("save")}
          </Btn>
        </div>
      </Card>

      {!hasRoom && (
        <Card className="p-6 text-center text-stone-500 mb-6" data-testid="no-room-notice">
          {t("setRoomFirst")}
        </Card>
      )}

      {hasRoom && viewMode === "list" && (
        <Card className="overflow-hidden" data-testid="tele-list-table">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("patient")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("date")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("time")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {activeAppts.length === 0 ? (
                  <tr><td colSpan={4} className="px-5 py-8 text-center text-stone-500">{t("noData")}</td></tr>
                ) : activeAppts.map((a, i) => (
                  <tr key={a.id} data-testid={`tele-row-${a.id}`} className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3 font-semibold text-moneygreen-800">{a.patient_name}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{a.date}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{a.time || "—"}</td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        <Btn variant="ghost" onClick={openMyRoom} data-testid={`tele-row-join-${a.id}`} className="!px-2" title={t("startVisit")}><ExternalLink className="w-4 h-4" /></Btn>
                        <Btn variant="ghost" onClick={() => invite(a, false)} disabled={inviting === a.id} data-testid={`tele-row-copylink-${a.id}`} className="!px-2" title={t("copyPatientLink")}>
                          {inviting === a.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Copy className="w-4 h-4" />}
                        </Btn>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {hasRoom && viewMode === "cards" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {activeAppts.map((a) => (
            <Card key={a.id} className="p-5" data-testid={`tele-appt-${a.id}`}>
              <p className="font-heading font-bold text-moneygreen-800">{a.patient_name}</p>
              <p className="text-sm text-stone-500 flex items-center gap-1.5 mt-1 mb-4">
                <Calendar className="w-4 h-4" /> {a.date} {a.time && `· ${a.time}`}
              </p>
              <div className="flex flex-col gap-2">
                <Btn onClick={openMyRoom} data-testid={`tele-join-${a.id}`} className="w-full">
                  <ExternalLink className="w-4 h-4" />{t("startVisit")}
                </Btn>
                <Btn variant="outline" onClick={() => invite(a, false)} disabled={inviting === a.id} data-testid={`tele-copylink-${a.id}`} className="w-full">
                  {inviting === a.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Copy className="w-4 h-4" />}{t("copyPatientLink")}
                </Btn>
              </div>
            </Card>
          ))}
          {activeAppts.length === 0 && (
            <Card className="p-6 text-center text-stone-500 col-span-full">{t("noData")}</Card>
          )}
        </div>
      )}
    </div>
  );
}
