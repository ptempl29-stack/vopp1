// UI permission gating — mirrors backend require_roles(). Admin can do everything.
const rules = {
  patients: ["doctor", "nurse", "receptionist"],
  appointments: ["doctor", "nurse", "receptionist"],
  notes: ["doctor", "nurse"],
  invoices: ["biller", "receptionist"],
  cpt: ["biller"],
  forms: ["doctor", "nurse", "receptionist", "biller"],
  messages: ["doctor", "nurse", "receptionist", "biller"],
};

export function can(role, resource) {
  if (role === "admin") return true;
  return (rules[resource] || []).includes(role);
}
