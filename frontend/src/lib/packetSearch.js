// Client Packets search: match a typed query against the patient's name.
// (A packet saved without a patient name falls back to the packet name, which
// normally starts with the patient's name.) Matching is case-insensitive.
export function filterPacketsByPatient(packets, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return packets;
  return packets.filter((p) => ((p.patient_name || p.name || "").toLowerCase()).includes(q));
}
