import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Btn, Card, Field, inputCls } from "../components/ui-kit";
import { Video, PhoneOff, Calendar } from "lucide-react";

export default function Telehealth() {
  const { t } = useLang();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [appts, setAppts] = useState([]);
  const [room, setRoom] = useState(params.get("room") || "");
  const [peer, setPeer] = useState(params.get("name") || "");
  const [active, setActive] = useState(!!params.get("room"));
  const containerRef = useRef(null);
  const apiRef = useRef(null);

  useEffect(() => { api.get("/appointments").then((r) => setAppts(r.data)).catch(() => {}); }, []);

  const activeAppts = useMemo(() => appts.filter((a) => a.status !== "cancelled"), [appts]);

  useEffect(() => {
    if (!active || !room) return;
    const load = () => {
      if (!window.JitsiMeetExternalAPI || !containerRef.current) return;
      apiRef.current = new window.JitsiMeetExternalAPI("meet.jit.si", {
        roomName: room,
        parentNode: containerRef.current,
        width: "100%", height: "100%",
        userInfo: { displayName: user?.name || "Clinician" },
        configOverwrite: { prejoinPageEnabled: false, startWithAudioMuted: false },
        interfaceConfigOverwrite: { MOBILE_APP_PROMO: false },
      });
    };
    if (window.JitsiMeetExternalAPI) load();
    else {
      const s = document.createElement("script");
      s.src = "https://meet.jit.si/external_api.js";
      s.async = true; s.onload = load;
      document.body.appendChild(s);
    }
    return () => { if (apiRef.current) { apiRef.current.dispose(); apiRef.current = null; } };
  }, [active, room, user]);

  const start = (r, name) => { setRoom(r); setPeer(name); setActive(true); setParams({ room: r, name: name || "" }); };
  const end = () => {
    if (apiRef.current) { apiRef.current.dispose(); apiRef.current = null; }
    setActive(false); setRoom(""); setParams({});
  };
  const startAdhoc = () => start(`vpp-${Date.now().toString(36)}`, "");

  if (active && room) {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">{t("telehealth")}</p>
            <h1 className="font-heading text-2xl font-extrabold text-moneygreen-800">{peer || room}</h1>
          </div>
          <Btn variant="danger" onClick={end} data-testid="end-call-btn"><PhoneOff className="w-4 h-4" />{t("endCall")}</Btn>
        </div>
        <div ref={containerRef} data-testid="jitsi-container"
          className="w-full h-[70vh] rounded-lg overflow-hidden border border-border bg-moneygreen-900" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t("telehealth")} subtitle={t("roomReady")}
        action={<Btn onClick={startAdhoc} data-testid="start-adhoc-btn"><Video className="w-4 h-4" />{t("startTelehealth")}</Btn>} />

      <Card className="p-6 mb-6 bg-moneygreen-50 border-moneygreen-100">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-md bg-moneygreen-600 flex items-center justify-center">
            <Video className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="font-heading font-bold text-moneygreen-800">{t("startTelehealth")}</p>
            <p className="text-sm text-stone-500">{t("selectAppt")}</p>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {activeAppts.map((a) => (
          <Card key={a.id} className="p-5" data-testid={`tele-appt-${a.id}`}>
            <p className="font-heading font-bold text-moneygreen-800">{a.patient_name}</p>
            <p className="text-sm text-stone-500 flex items-center gap-1.5 mt-1 mb-4">
              <Calendar className="w-4 h-4" /> {a.date} {a.time && `· ${a.time}`}
            </p>
            <Btn onClick={() => start(`vpp-${a.id}`, a.patient_name)} data-testid={`tele-join-${a.id}`} className="w-full">
              <Video className="w-4 h-4" />{t("startVisit")}
            </Btn>
          </Card>
        ))}
      </div>
    </div>
  );
}
