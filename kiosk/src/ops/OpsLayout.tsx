import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useSocket } from "../net/socket";
import { getOperatorToken, setOperatorToken } from "./api";

// Rule 2.3.4 (plan): while thresholds are provisional/uncalibrated the operator view shows a banner.
// The flag comes from the server's hello_ack, not from the client.
export function OpsLayout() {
  const { socket, state } = useSocket();
  const provisional = socket.helloAck?.policy.provisional;
  const [token, setToken] = useState(getOperatorToken());
  return (
    <div className="ops">
      {provisional && <div className="banner">PROVISIONAL THRESHOLDS — not calibrated</div>}
      <header>
        <strong>HID Liveness Kiosk · Operator</strong>
        <nav>
          <NavLink to="/ops" end>
            Status
          </NavLink>
          <NavLink to="/ops/spike">Spike</NavLink>
          <NavLink to="/ops/camera-probe">Camera probe</NavLink>
          <NavLink to="/ops/collect">Collect</NavLink>
          <NavLink to="/ops/enroll">Enroll</NavLink>
          <NavLink to="/ops/review">Review</NavLink>
          <NavLink to="/ops/results">Results</NavLink>
        </nav>
        <input
          type="password"
          placeholder="operator token"
          value={token}
          onChange={(e) => {
            setToken(e.target.value);
            setOperatorToken(e.target.value);
          }}
          style={{ width: 150 }}
        />
        <span className={`pill ${state}`}>{state}</span>
      </header>
      <Outlet />
    </div>
  );
}
