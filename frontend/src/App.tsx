import { AppShell } from "./components/AppShell";
import { SystemStatusPage } from "./pages/SystemStatusPage";
import { useSystemStatus } from "./pages/useSystemStatus";

export function App() {
  const status = useSystemStatus();
  return (
    <AppShell version={status.version}>
      <SystemStatusPage status={status} />
    </AppShell>
  );
}
