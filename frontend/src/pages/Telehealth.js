import React, { useEffect, useMemo, useState } from "react";
import api, { apiErr } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Btn, Card, inputCls } from "../components/ui-kit";
import { Video, Calendar, Save, Link2, Mail, ShieldCheck, ExternalLink, Loader2, Copy } from "lucide-react";
import { toast } from "sonner";

export default function Telehealth() {
  const { t } = useLang();
  const { user, refreshUser } = useAuth();
  const [appts, setAppts] = useState([]);
  const [room, setRoom] = useState(user?.doxy_room || "");
  const [savingRoom, setSavingRoom] = useState(false);
  const [inviting, setInviting] = useState(null);

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
        action={hasRoom && <Btn onClick={openMyRoom} data-testid="open-room-btn"><Video className="w-4 h-4" />{t("openMyRoom")}</Btn>} />

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

      {hasRoom && (
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
