import { Navigate, Route, Routes } from "react-router-dom";
import { KioskPage } from "./kiosk/KioskPage";
import { NotImplemented } from "./components/NotImplemented";
import { OpsLayout } from "./ops/OpsLayout";
import { OpsStatus } from "./ops/OpsStatus";
import { CameraProbe } from "./ops/CameraProbe";
import { SpikePage } from "./ops/SpikePage";

// Routes follow plan §14. Anything not built in the current milestone renders a plain notice, never mock data.
export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/ops" replace />} />
      <Route path="/kiosk" element={<KioskPage />} />
      <Route path="/ops" element={<OpsLayout />}>
        <Route index element={<OpsStatus />} />
        <Route path="spike" element={<SpikePage />} />
        <Route path="camera-probe" element={<CameraProbe />} />
        <Route path="attempt/:id" element={<NotImplemented what="Evidence view" milestone="M7 (T7.1)" />} />
        <Route path="compare" element={<NotImplemented what="Compare view" milestone="M7 (T7.1)" />} />
        <Route path="review" element={<NotImplemented what="Manual review queue" milestone="M5 (T5.6)" />} />
        <Route path="enroll" element={<NotImplemented what="Enrollment" milestone="M3 (T3.6)" />} />
        <Route path="collect" element={<NotImplemented what="Collect mode" milestone="M4 (T4.1)" />} />
        <Route path="calibrate" element={<NotImplemented what="Kiosk calibration" milestone="M7 (T7.3)" />} />
        <Route path="results" element={<NotImplemented what="Judge dashboard" milestone="M7 (T7.2)" />} />
      </Route>
      <Route path="*" element={<NotImplemented what="This page" milestone="n/a (unknown route)" />} />
    </Routes>
  );
}
