// Robust multi-page printing: clone the target node into a top-level holder
// so content flows across pages (avoids overlap caused by absolutely
// positioned content inside scrollable modals).
export function printSection(nodeId) {
  const src = document.getElementById(nodeId);
  if (!src) { window.print(); return; }
  const existing = document.getElementById("print-holder");
  if (existing) existing.remove();
  const holder = document.createElement("div");
  holder.id = "print-holder";
  holder.innerHTML = src.innerHTML;
  document.body.appendChild(holder);
  document.body.classList.add("printing");
  const cleanup = () => {
    document.body.classList.remove("printing");
    const h = document.getElementById("print-holder");
    if (h) h.remove();
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  setTimeout(() => window.print(), 60);
}
