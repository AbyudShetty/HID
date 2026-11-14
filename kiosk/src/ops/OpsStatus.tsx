import { useSocket } from "../net/socket";

export function OpsStatus() {
  const { socket, state } = useSocket();
  const ack = socket.helloAck;
  return (
    <div className="panel">
      <h2>Connection</h2>
      <table>
        <tbody>
          <tr><th>State</th><td>{state}</td></tr>
          <tr><th>Server version</th><td>{ack?.server_version ?? "—"}</td></tr>
          <tr><th>Policy</th><td>{ack ? `${ack.policy.version} (${ack.policy.provisional ? "provisional" : "calibrated"})` : "—"}</td></tr>
          <tr><th>Capture config</th><td>{ack ? JSON.stringify(ack.capture_config) : "—"}</td></tr>
          <tr><th>Reconnects</th><td>{socket.reconnects}</td></tr>
          <tr><th>Last error</th><td>{socket.lastError ?? "none"}</td></tr>
        </tbody>
      </table>
    </div>
  );
}
