import { useCallback, useEffect, useRef, useState } from "react";
import {
  FiRefreshCw,
  FiSmartphone,
  FiXCircle,
  FiWifi,
  FiCpu,
  FiHelpCircle,
  FiCopy,
  FiCheck,
  FiShield,
  FiSend,
} from "react-icons/fi";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader } from "@/components/PageHeader";
import {
  connectService,
  type ConnectDevice,
  type ConnectTask,
  type PairingSession,
} from "@/services/connect";

const ACTIVE = new Set(["dispatched", "queued_offline", "started", "in_progress"]);

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "SAM Connect request failed.";
}

export function ConnectPage() {
  const [devices, setDevices] = useState<ConnectDevice[]>([]);
  const [pairing, setPairing] = useState<PairingSession | null>(null);
  const [tasks, setTasks] = useState<ConnectTask[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [title] = useState("SAM update");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [revokingDevice, setRevokingDevice] = useState<ConnectDevice | null>(null);
  const [activeTab, setActiveTab] = useState<"wifi" | "usb" | "troubleshooting">("wifi");
  const [copiedToken, setCopiedToken] = useState(false);

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

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const act = async (operation: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await operation();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const startPairing = () =>
    act(async () => {
      const session = await connectService.startPairing();
      setPairing(session);
      setNotice("One-time pairing token created. Enter it in SAM Mobile Companion.");
    });

  const revoke = (device: ConnectDevice) =>
    act(async () => {
      await connectService.revokeDevice(device.id);
      setNotice(`${device.device_name || device.external_id} was revoked.`);
      setRevokingDevice(null);
      await refresh();
    });

  const send = () => {
    if (!deviceId || !message.trim()) return;
    void act(async () => {
      const task = await connectService.createNotificationTask(
        deviceId,
        title.trim() || "SAM update",
        message.trim()
      );
      setTasks((current) =>
        [task, ...current.filter((item) => item.task_id !== task.task_id)].slice(0, 10)
      );
      setMessage("");
      setNotice("Notification dispatched to phone. Tap notification on mobile to view.");
    });
  };

  const cancel = (taskId: string) =>
    act(async () => {
      await connectService.cancelTask(taskId);
      await refresh();
    });

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-12">
      <PageHeader
        title="Device Connect"
        mode="live"
        description="Pair and sync trusted mobile devices with SAM. Supports local Wi-Fi pairing and high-speed USB reverse tunnel."
      />

      {error && (
        <div className="rounded-md border border-danger/25 bg-danger/10 p-3 text-xs text-danger">
          {error}
        </div>
      )}

      {notice && (
        <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 p-3 text-xs text-emerald-400">
          {notice}
        </div>
      )}

      {/* Connection Methods Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-line pb-2">
        <button
          type="button"
          onClick={() => setActiveTab("wifi")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "wifi"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiWifi size={13} className="text-blue-400" /> Wi-Fi Pairing
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("usb")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "usb"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiCpu size={13} className="text-amber-400" /> USB Cable (Fastest)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("troubleshooting")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "troubleshooting"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiHelpCircle size={13} className="text-ember" /> Connection Guide & Troubleshooting
        </button>
      </div>

      {/* Tab 1: Wi-Fi Pairing */}
      {activeTab === "wifi" && (
        <Card className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold text-ink text-sm">Pair via Local Wi-Fi</h2>
              <p className="mt-1 text-xs text-mute">
                Ensure your Mac and phone are connected to the same Wi-Fi network or mobile hotspot.
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={startPairing} loading={busy}>
              <FiSmartphone size={13} /> Generate Pairing Key
            </Button>
          </div>

          {pairing ? (
            <div className="space-y-3 rounded-md border border-line bg-surface-raised p-3.5 text-xs">
              <div className="flex items-center justify-between border-b border-line pb-2">
                <span className="font-semibold text-ink text-xs">Active Pairing Token</span>
                <span className="text-[10px] text-mute font-mono-data">
                  Expires in ~10 mins
                </span>
              </div>

              <div className="grid gap-2 font-mono-data text-xs">
                <div className="flex items-center justify-between bg-surface p-2 rounded border border-line">
                  <span className="text-mute">Server Address:</span>
                  <code className="text-ink font-semibold">http://{pairing.host}:{pairing.port}</code>
                </div>

                <div className="flex items-center justify-between bg-surface p-2 rounded border border-line">
                  <span className="text-mute">One-Time Token:</span>
                  <div className="flex items-center gap-2">
                    <code className="text-ember font-bold break-all">{pairing.token}</code>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(pairing.token)}
                      className="p-1 text-mute hover:text-ink"
                      title="Copy Token"
                    >
                      {copiedToken ? <FiCheck size={12} className="text-success" /> : <FiCopy size={12} />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-mute space-y-1">
                <p className="font-medium text-ink">Instructions for Mobile App:</p>
                <ol className="list-decimal list-inside space-y-0.5">
                  <li>Open SAM Companion App on your Android device.</li>
                  <li>Tap <strong>"Pair New PC"</strong>.</li>
                  <li>Enter the server address and paste the token above.</li>
                </ol>
              </div>
            </div>
          ) : (
            <div className="rounded border border-dashed border-line p-4 text-center text-xs text-mute">
              Click <strong>"Generate Pairing Key"</strong> to start a secure pairing session.
            </div>
          )}

          <p className="text-[11px] text-mute">
            🔒 Local connection: Device requests are cryptographically verified using SHA-256 HMAC tokens.
          </p>
        </Card>
      )}

      {/* Tab 2: USB Cable ADB Tunnel */}
      {activeTab === "usb" && (
        <Card className="space-y-4">
          <div>
            <h2 className="font-semibold text-ink text-sm">USB Cable Connection (Zero-Latency, No Wi-Fi Needed)</h2>
            <p className="mt-1 text-xs text-mute">
              The fastest and most stable way to connect your phone, bypassing hotel/office Wi-Fi firewalls completely.
            </p>
          </div>

          <div className="space-y-3 rounded-md border border-line bg-surface-raised p-4 text-xs space-y-2.5">
            <h3 className="font-medium text-ink text-xs">3-Step USB Setup:</h3>
            <ol className="list-decimal list-inside space-y-2 text-mute">
              <li>
                Connect phone to Mac using a USB cable. On Android, enable <strong>Developer Options</strong> &rarr; <strong>USB Debugging</strong>.
              </li>
              <li>
                In your Mac Terminal, run this one-line command to reverse-tunnel port 8420:
                <div className="mt-1 flex items-center justify-between rounded bg-surface p-2 border border-line font-mono-data text-[11px]">
                  <code className="text-ember">adb reverse tcp:8420 tcp:8420</code>
                  <button
                    type="button"
                    onClick={() => copyToClipboard("adb reverse tcp:8420 tcp:8420")}
                    className="text-mute hover:text-ink"
                    title="Copy command"
                  >
                    <FiCopy size={12} />
                  </button>
                </div>
              </li>
              <li>
                In the SAM mobile app, simply connect to:
                <div className="mt-1 rounded bg-surface p-2 border border-line font-mono-data text-[11px] text-ink font-semibold">
                  http://127.0.0.1:8420
                </div>
              </li>
            </ol>
          </div>

          <p className="text-[11px] text-emerald-400">
            ✓ USB Reverse Tunneling routes packets over the physical wire with sub-millisecond response times.
          </p>
        </Card>
      )}

      {/* Tab 3: Troubleshooting Guide */}
      {activeTab === "troubleshooting" && (
        <Card className="space-y-4">
          <div>
            <h2 className="font-semibold text-ink text-sm">Connection Troubleshooting Assistant</h2>
            <p className="mt-1 text-xs text-mute">
              Common issues preventing mobile connection and how to resolve them immediately.
            </p>
          </div>

          <div className="space-y-3 text-xs">
            <div className="rounded border border-line bg-surface-raised p-3 space-y-1">
              <h4 className="font-medium text-ink flex items-center gap-1.5">
                <span className="text-amber-400 font-bold">1.</span> Phone says "Connection Refused" or "Cannot Reach PC"
              </h4>
              <p className="text-mute">
                <strong>Cause:</strong> macOS Application Firewall is blocking incoming port 8420, or phone and Mac are on different subnets.
              </p>
              <p className="text-mute">
                <strong>Fix:</strong> Open <em>System Settings &rarr; Network &rarr; Firewall &rarr; Options</em> and ensure SAM allows incoming connections. Alternatively, turn on your phone's personal hotspot and connect your Mac to it.
              </p>
            </div>

            <div className="rounded border border-line bg-surface-raised p-3 space-y-1">
              <h4 className="font-medium text-ink flex items-center gap-1.5">
                <span className="text-amber-400 font-bold">2.</span> Hotel / Campus / Office Wi-Fi Blocks Peer Devices
              </h4>
              <p className="text-mute">
                <strong>Cause:</strong> Enterprise routers enable "AP Isolation" or "Client Isolation", which forbids devices from talking to each other.
              </p>
              <p className="text-mute">
                <strong>Fix:</strong> Switch to the <strong>USB Cable Method</strong> (Tab 2) or connect both devices to a mobile hotspot.
              </p>
            </div>

            <div className="rounded border border-line bg-surface-raised p-3 space-y-1">
              <h4 className="font-medium text-ink flex items-center gap-1.5">
                <span className="text-amber-400 font-bold">3.</span> How to test if the gateway is running?
              </h4>
              <p className="text-mute">
                Open Safari or Chrome on your phone and browse to <code>http://&lt;your-mac-ip&gt;:8420/health</code>. You should see <code>{'{ "status": "ok" }'}</code>.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Trusted Devices Section */}
      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FiShield className="text-ember" />
            <h2 className="font-semibold text-ink text-sm">Paired Devices ({devices.length})</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void refresh()}>
            <FiRefreshCw size={13} /> Refresh
          </Button>
        </div>

        {devices.length === 0 ? (
          <p className="text-xs text-mute py-4 text-center border border-dashed border-line rounded">
            No mobile devices paired yet. Follow the steps above to pair your phone.
          </p>
        ) : (
          devices.map((device) => (
            <div
              key={device.id}
              className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-xs"
            >
              <div className="space-y-0.5">
                <div className="font-medium text-ink flex items-center gap-1.5">
                  <FiSmartphone size={14} className="text-ember" />
                  <span>{device.device_name || device.external_id}</span>
                </div>
                <div className="text-[11px] text-mute font-mono-data">
                  {device.platform || device.channel} · state: {device.connection_state} · status: {device.status}
                </div>
              </div>
              {device.status === "trusted" && (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setRevokingDevice(device)}
                  loading={busy}
                >
                  Revoke Trust
                </Button>
              )}
            </div>
          ))
        )}
      </Card>

      {/* Quick Mobile Notification Dispatch */}
      {devices.some((d) => d.status === "trusted") && (
        <Card className="space-y-3">
          <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
            <FiSend className="text-ember" /> Send Notification to Phone
          </h2>
          <div className="grid gap-3">
            <div>
              <label className="block text-xs text-mute mb-1">Target Phone</label>
              <select
                className="w-full rounded-md border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:outline-none"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
              >
                <option value="">Select paired phone...</option>
                {devices
                  .filter((d) => d.status === "trusted")
                  .map((d) => (
                    <option key={d.external_id} value={d.external_id}>
                      {d.device_name || d.external_id}
                    </option>
                  ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-mute mb-1">Message</label>
              <textarea
                className="w-full rounded-md border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:outline-none"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Alert text to display on mobile..."
                rows={2}
              />
            </div>

            <div className="flex justify-end">
              <Button
                variant="primary"
                size="sm"
                onClick={send}
                loading={busy}
                disabled={!deviceId || !message.trim()}
              >
                Send to Phone
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Recent Routed Tasks */}
      {tasks.length > 0 && (
        <Card className="space-y-3">
          <h2 className="font-semibold text-ink text-sm">Recent Mobile Tasks</h2>
          <div className="space-y-2">
            {tasks.map((task) => (
              <div
                key={task.task_id}
                className="flex items-center justify-between gap-3 border-t border-line pt-2 text-xs"
              >
                <div>
                  <div className="text-ink font-medium">
                    {task.status} · {task.action}
                  </div>
                  <div className="text-[11px] text-mute font-mono-data">
                    {task.last_message || task.error || task.task_id}
                  </div>
                </div>
                {ACTIVE.has(task.status) && (
                  <Button variant="ghost" size="sm" onClick={() => void cancel(task.task_id)}>
                    <FiXCircle size={13} /> Cancel
                  </Button>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={revokingDevice !== null}
        title="Revoke device trust?"
        description={`SAM will reject future requests from ${
          revokingDevice?.device_name || revokingDevice?.external_id || "this device"
        }. You can re-pair at any time.`}
        confirmLabel="Revoke trust"
        confirming={busy}
        onConfirm={() => {
          if (revokingDevice) void revoke(revokingDevice);
        }}
        onCancel={() => setRevokingDevice(null)}
      />
    </div>
  );
}
