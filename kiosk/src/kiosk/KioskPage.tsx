import { NotImplemented } from "../components/NotImplemented";

// The kiosk state machine and screens arrive in M3 (T3.4). The kiosk route never shows scores (plan §14.2).
export function KioskPage() {
  return (
    <main className="kiosk">
      <NotImplemented what="Kiosk screen" milestone="M3 (T3.4)" />
    </main>
  );
}
