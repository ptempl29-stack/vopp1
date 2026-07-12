// UI action-permission gating. Admin can do everything. Tab visibility is controlled
// separately by user.allowed_tabs (set by admin), not here.
const rules = {
  patients: ["doctor", "nurse", "receptionist"],
  appointments: ["doctor", "nurse", "receptionist", "psychologist"],
  notes: ["doctor", "nurse", "psychologist"],
  invoices: ["biller", "receptionist"],
  cpt: ["biller"],
  reports: ["biller"],
  forms: ["doctor", "nurse", "receptionist", "biller", "psychologist"],
  messages: ["doctor", "nurse", "receptionist", "biller", "psychologist"],
};

export function can(role, resource) {
  if (role === "admin") return true;
  return (rules[resource] || []).includes(role);
}
