import { filterPacketsByPatient } from "./packetSearch.js";

const P = [
  { id: 1, patient_name: "Brandon Whitfield", name: "Brandon Whitfield 10/01/2026 FMP Claim" },
  { id: 2, patient_name: "Printiss Temple", name: "x" },
  { id: 3, patient_name: "", name: "Saday Cabrera 09/01 FMP Claim" },
];
const ids = (q) => filterPacketsByPatient(P, q).map((p) => p.id);

test("empty or blank query shows every packet", () => {
  expect(ids("")).toEqual([1, 2, 3]);
  expect(ids("   ")).toEqual([1, 2, 3]);
});
test("matches patient name, case-insensitive and partial", () => {
  expect(ids("brandon")).toEqual([1]);
  expect(ids("TEMPLE")).toEqual([2]);
  expect(ids("whit")).toEqual([1]);
});
test("falls back to packet name only when there is no patient name", () => {
  expect(ids("saday")).toEqual([3]);
  expect(ids("fmp")).toEqual([3]);
});
test("no match returns an empty list", () => {
  expect(ids("zzz")).toEqual([]);
});
