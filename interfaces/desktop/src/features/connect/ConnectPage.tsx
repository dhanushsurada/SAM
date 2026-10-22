import { useCallback, useEffect, useRef, useState } from "react";
import { FiRefreshCw, FiSmartphone, FiXCircle } from "react-icons/fi";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader } from "@/components/PageHeader";
import { connectService, type ConnectDevice, type ConnectTask, type PairingSession } from "@/services/connect";

const ACTIVE = new Set(["dispatched", "queued_offline", "started", "in_progress"]);

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "SAM Connect request failed.";
}

export function ConnectPage() {
  const [devices, setDevices] = useState<ConnectDevice[]>([]);
  const [pairing, setPairing] = useState<PairingSession | null>(null);
  const [tasks, setTasks] = useState<ConnectTask[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [title, setTitle] = useState("SAM update");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [revokingDevice, setRevokingDevice] = useState<ConnectDevice | null>(null);
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;

  const refresh = useCallback(async () => {
    try {
      const [listed, ...updatedTasks] = await Promise.all([
        connectService.listDevices(),
        ...tasksRef.current.map((task) => connectService.getTask(task.task_id).catch(() => task)),
      ]);
      setDevices(listed);
      setTasks(updatedTasks);
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const interval = window.setInterval(() => { void refresh(); }, 5000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const act = async (operation: () => Promise<void>) => {
    setBusy(true); setError(null); setNotice(null);
    try { await operation(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  const startPairing = () => act(async () => {
    setPairing(await connectService.startPairing());
    setNotice("One-time pairing token created. It expires shortly; share it only with the phone you are pairing.");
  });

  const revoke = (device: ConnectDevice) => act(async () => {
    await connectService.revokeDevice(device.id);
    setNotice(`${device.device_name || device.external_id} was revoked.`);
    setRevokingDevice(null);
    await refresh();
  });

  const send = () => {
    if (!deviceId || !message.trim()) return;
    void act(async () => {
      const task = await connectService.createNotificationTask(deviceId, title.trim() || "SAM update", message.trim());
      setTasks((current) => [task, ...current.filter((item) => item.task_id !== task.task_id)].slice(0, 10));
      setMessage("");
      setNotice("Task sent. The phone requires a user tap before it posts the notification.");
    });
  };

  const cancel = (taskId: string) => act(async () => {
    await connectService.cancelTask(taskId);
    await refresh();
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader title="Connect" description="Pair trusted devices and route a supported notification task." />
      <Card className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-semibold text-ink">Pair a device</h2>
            <p className="mt-1 text-sm text-mute">Create a short-lived one-time token, then enter it in SAM for Android.</p>
          </div>
          <Button onClick={startPairing} loading={busy}><FiSmartphone /> New pairing token</Button>
        </div>
        {pairing && <div className="rounded-md border border-line bg-void p-3 text-sm">
          <div><span className="text-mute">Server:</span> <code>http://{pairing.host}:{pairing.port}</code></div>
          <div className="mt-2"><span className="text-mute">Token:</span> <code className="break-all">{pairing.token}</code></div>
          <div className="mt-2 text-xs text-mute">Expires {new Date(pairing.expires_at).toLocaleString()} · protocol {pairing.v}</div>
        </div>}
        <p className="text-xs text-warn">Connect signs requests but HTTP does not encrypt task content. Pair and use devices only on a trusted local network; do not expose this API to the public internet.</p>
      </Card>

      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-ink">Trusted devices</h2>
          <Button variant="ghost" size="sm" onClick={() => void refresh()}><FiRefreshCw /> Refresh</Button>
        </div>
        {devices.length === 0 ? <p className="text-sm text-mute">No paired devices yet.</p> : devices.map((device) => (
          <div key={device.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
            <div>
              <div className="font-medium text-ink">{device.device_name || device.external_id}</div>
              <div className="text-xs text-mute">{device.platform || device.channel} · {device.connection_state} · {device.status}</div>
              <div className="mt-1 text-xs text-mute">Capabilities: {Object.entries(device.capabilities || {}).map(([name, value]) => `${name} ${value.available ? "available" : "unavailable"} (${value.permission})`).join(", ") || "none reported"}</div>
            </div>
            {device.status === "trusted" && <Button variant="danger" size="sm" onClick={() => setRevokingDevice(device)} loading={busy}>Revoke trust</Button>}
          </div>
        ))}
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold text-ink">Send notification task</h2>
        <label className="block text-sm text-mute">Trusted phone
          <select className="mt-1 w-full rounded-md border border-line bg-void px-3 py-2 text-ink" value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
            <option value="">Choose a device</option>
            {devices.filter((device) => device.status === "trusted" && device.capabilities?.notifications?.available).map((device) =>
              <option key={device.external_id} value={device.external_id}>{device.device_name || device.external_id}</option>)}
          </select>
        </label>
        <label className="block text-sm text-mute">Title<input className="mt-1 w-full rounded-md border border-line bg-void px-3 py-2 text-ink" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={80} /></label>
        <label className="block text-sm text-mute">Message<textarea className="mt-1 w-full rounded-md border border-line bg-void px-3 py-2 text-ink" value={message} onChange={(event) => setMessage(event.target.value)} rows={3} maxLength={500} /></label>
        <Button onClick={send} loading={busy} disabled={!deviceId || !message.trim()}>Send to phone</Button>
        <p className="text-xs text-mute">The Android client supports only <code>show_notification</code> here. The recipient must tap to run it, and notification permission must be enabled.</p>
      </Card>

      {tasks.length > 0 && <Card className="space-y-3">
        <h2 className="font-semibold text-ink">Recent routed tasks</h2>
        {tasks.map((task) => <div key={task.task_id} className="flex items-center justify-between gap-3 border-t border-line pt-3 text-sm">
          <div><div className="text-ink">{task.status} · {task.action}</div><div className="text-xs text-mute">{task.last_message || task.error || task.task_id}</div></div>
          {ACTIVE.has(task.status) && <Button variant="ghost" size="sm" onClick={() => void cancel(task.task_id)}><FiXCircle /> Cancel</Button>}
        </div>)}
      </Card>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {notice && <p role="status" className="text-sm text-mute">{notice}</p>}
      <ConfirmDialog
        open={revokingDevice !== null}
        title="Revoke device trust?"
        description={`SAM will reject future requests from ${revokingDevice?.device_name || revokingDevice?.external_id || "this device"}. You can pair it again later.`}
        confirmLabel="Revoke trust"
        confirming={busy}
        onConfirm={() => { if (revokingDevice) void revoke(revokingDevice); }}
        onCancel={() => setRevokingDevice(null)}
      />
    </div>
  );
}
