export function NotImplemented({ what, milestone }: { what: string; milestone: string }) {
  return (
    <div className="panel">
      <h2>{what}</h2>
      <p>Not implemented in this milestone. Scheduled for {milestone} in plan.md. Nothing is simulated here.</p>
    </div>
  );
}
