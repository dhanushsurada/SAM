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
  FiLayers,
  FiMessageSquare,
  FiRadio,
  FiExternalLink,
  FiClipboard,
  FiCheckCircle,
  FiCompass,
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
import {
  bridgesService,
  type BridgesStatusResponse,
  type FabricTopologyResponse,
  type BridgePairingResponse,
} from "@/services/bridges";

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

  // Omnichannel Bridge & Fabric States
  const [activeTab, setActiveTab] = useState<"fabric" | "whatsapp" | "telegram" | "ios" | "wifi" | "usb" | "troubleshooting">("fabric");
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [bridgeStatus, setBridgeStatus] = useState<BridgesStatusResponse | null>(null);
  const [topology, setTopology] = useState<FabricTopologyResponse | null>(null);
  const [activeBridgePairing, setActiveBridgePairing] = useState<BridgePairingResponse | null>(null);
  const [clipboardInput, setClipboardInput] = useState("");
  const [broadcastText, setBroadcastText] = useState("");

  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;

  const refresh = useCallback(async () => {
    try {
      const [listed, bStatus, topo, ...updatedTasks] = await Promise.all([
        connectService.listDevices().catch(() => []),
        bridgesService.getStatus().catch(() => null),
        bridgesService.getTopology().catch(() => null),
        ...tasksRef.current.map((task) => connectService.getTask(task.task_id).catch(() => task)),
      ]);
      setDevices(listed);
      if (bStatus) setBridgeStatus(bStatus);
      if (topo) setTopology(topo);
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

  const pairBridgeChannel = (channel: string) =>
    act(async () => {
      const resp = await bridgesService.pairChannel(channel);
      setActiveBridgePairing(resp);
      setNotice(`Generated pairing credentials for ${channel.toUpperCase()}.`);
    });

  const toggleBridgeStatus = (channel: string, currentStatus: string) =>
    act(async () => {
      if (currentStatus === "active") {
        await bridgesService.stopBridge(channel);
        setNotice(`Stopped ${channel.toUpperCase()} bridge.`);
      } else {
        await bridgesService.startBridge(channel);
        setNotice(`Started ${channel.toUpperCase()} bridge.`);
      }
      await refresh();
    });

  const syncClipboardToMesh = () => {
    if (!clipboardInput.trim()) return;
    act(async () => {
      await bridgesService.setClipboard(clipboardInput.trim(), "desktop");
      setClipboardInput("");
      setNotice("Clipboard synced to mesh fabric. Available on all connected devices.");
      await refresh();
    });
  };

  const broadcastAll = () => {
    if (!broadcastText.trim()) return;
    act(async () => {
      const res = await bridgesService.broadcast(broadcastText.trim());
      setBroadcastText("");
      const successCount = Object.values(res.results).filter(Boolean).length;
      setNotice(`Broadcast dispatched to ${successCount} channels.`);
      await refresh();
    });
  };

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

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(label);
    setTimeout(() => setCopiedToken(null), 2000);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      <PageHeader
        title="Omnichannel Device Fabric & Bridges"
        mode="live"
        description="Unified interconnectivity across macOS, iPhone (Siri & Action Button), Android, WhatsApp, Telegram, and cross-device Matter flows."
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

      {/* Omnichannel Overview Bar */}
      {bridgeStatus && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="rounded-md border border-line bg-surface-raised p-3">
            <span className="text-[11px] text-mute block">Total Mesh Nodes</span>
            <span className="font-semibold text-ink text-base mt-0.5 block">{bridgeStatus.mesh_nodes} active</span>
          </div>
          <div className="rounded-md border border-line bg-surface-raised p-3">
            <span className="text-[11px] text-mute block">Active Bridges</span>
            <span className="font-semibold text-emerald-400 text-base mt-0.5 block">{bridgeStatus.stats.active_bridges} running</span>
          </div>
          <div className="rounded-md border border-line bg-surface-raised p-3">
            <span className="text-[11px] text-mute block">Trusted Devices</span>
            <span className="font-semibold text-ink text-base mt-0.5 block">{bridgeStatus.stats.total_trusted_devices} paired</span>
          </div>
          <div className="rounded-md border border-line bg-surface-raised p-3">
            <span className="text-[11px] text-mute block">Shared Clipboard</span>
            <span className={`font-semibold text-base mt-0.5 block ${bridgeStatus.stats.clipboard_synced ? "text-blue-400" : "text-mute"}`}>
              {bridgeStatus.stats.clipboard_synced ? "Synced" : "Empty"}
            </span>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line pb-2">
        <button
          type="button"
          onClick={() => setActiveTab("fabric")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "fabric"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiLayers size={13} className="text-purple-400" /> Device Fabric & Matter
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("whatsapp")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "whatsapp"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiMessageSquare size={13} className="text-emerald-400" /> WhatsApp Bridge
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("telegram")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "telegram"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiSend size={13} className="text-sky-400" /> Telegram Bot
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("ios")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "ios"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiRadio size={13} className="text-pink-400" /> Apple iOS & Siri
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("wifi")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeTab === "wifi"
              ? "bg-surface-raised text-ink border border-line"
              : "text-mute hover:text-ink hover:bg-surface"
          }`}
        >
          <FiWifi size={13} className="text-blue-400" /> Android / Wi-Fi
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
          <FiCpu size={13} className="text-amber-400" /> USB Cable
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
          <FiHelpCircle size={13} className="text-ember" /> Guide
        </button>
      </div>

      {/* Tab: Device Fabric & Matter Flow */}
      {activeTab === "fabric" && (
        <div className="space-y-4">
          <Card className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
                  <FiLayers className="text-purple-400" /> Unified Device Fabric Topology
                </h2>
                <p className="mt-1 text-xs text-mute">
                  All active channels form a synchronized mesh. Tasks, context, and Matter automation flows migrate seamlessly between devices.
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => void refresh()} loading={busy}>
                <FiRefreshCw size={13} /> Refresh Topology
              </Button>
            </div>

            {topology && (
              <div className="space-y-3">
                <div className="rounded-md border border-line bg-surface-raised p-3">
                  <div className="flex items-center justify-between text-xs border-b border-line pb-2 mb-2">
                    <span className="font-medium text-ink">Fabric Hub Node</span>
                    <span className="text-emerald-400 font-mono-data text-[11px]">STATUS: {topology.hub.status.toUpperCase()}</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono-data">
                    <div>
                      <span className="text-mute block">Node:</span>
                      <span className="text-ink font-semibold">{topology.hub.name}</span>
                    </div>
                    <div>
                      <span className="text-mute block">Platform:</span>
                      <span className="text-ink">{topology.hub.platform}</span>
                    </div>
                    <div>
                      <span className="text-mute block">Protocol:</span>
                      <span className="text-ink">{topology.hub.protocol_version}</span>
                    </div>
                    <div>
                      <span className="text-mute block">Mesh Total:</span>
                      <span className="text-ink">{topology.total_nodes} nodes</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <h3 className="text-xs font-medium text-ink">Connected Mesh Nodes ({topology.nodes.length})</h3>
                  <div className="grid gap-2">
                    {topology.nodes.map((node) => (
                      <div
                        key={node.node_id}
                        className="flex items-center justify-between p-2.5 rounded border border-line bg-surface text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <FiCheckCircle size={14} className="text-emerald-400" />
                          <div>
                            <div className="font-medium text-ink">{node.device_name}</div>
                            <div className="text-[10px] text-mute font-mono-data">
                              Type: {node.device_type} · ID: {node.node_id}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {node.capabilities.map((cap) => (
                            <span
                              key={cap}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-surface-raised border border-line text-mute font-mono-data"
                            >
                              {cap}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Card>

          {/* Cross-Device Shared Clipboard Card */}
          <Card className="space-y-3">
            <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
              <FiClipboard className="text-blue-400" /> Cross-Device Shared Clipboard
            </h2>
            <p className="text-xs text-mute">
              Paste text or URLs here to instantly sync across your Mac, iPhone, and Android devices in the mesh.
            </p>

            {topology?.shared_clipboard.has_content && (
              <div className="rounded border border-line bg-surface p-3 text-xs space-y-1">
                <div className="flex items-center justify-between text-[11px] text-mute border-b border-line pb-1">
                  <span>Last synced from: <strong>{topology.shared_clipboard.source}</strong></span>
                  <span className="font-mono-data text-[10px]">{topology.shared_clipboard.updated_at}</span>
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <input
                type="text"
                className="flex-1 rounded-md border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:outline-none"
                placeholder="Enter text or URL to sync across mesh devices..."
                value={clipboardInput}
                onChange={(e) => setClipboardInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && syncClipboardToMesh()}
              />
              <Button variant="primary" size="sm" onClick={syncClipboardToMesh} loading={busy} disabled={!clipboardInput.trim()}>
                Sync to Mesh
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Tab: WhatsApp Bridge */}
      {activeTab === "whatsapp" && (
        <Card className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
                <FiMessageSquare className="text-emerald-400" /> WhatsApp Omnichannel Bridge
              </h2>
              <p className="mt-1 text-xs text-mute">
                Send instructions, trigger Mac actions, and receive proactive briefings directly inside WhatsApp.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleBridgeStatus("whatsapp", bridgeStatus?.channels.whatsapp.status || "")}
                loading={busy}
              >
                {bridgeStatus?.channels.whatsapp.status === "active" ? "Pause Bridge" : "Activate Bridge"}
              </Button>
              <Button variant="primary" size="sm" onClick={() => pairBridgeChannel("whatsapp")} loading={busy}>
                <FiMessageSquare size={13} /> Pair WhatsApp
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Status</span>
              <span className="font-semibold text-ink capitalize mt-0.5 block">
                {bridgeStatus?.channels.whatsapp.status || "ready"}
              </span>
            </div>
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Phone Number ID</span>
              <span className="font-mono-data text-ink text-[11px] mt-0.5 block truncate">
                {bridgeStatus?.channels.whatsapp.phone_number_id || "Configured in Settings"}
              </span>
            </div>
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Paired Senders</span>
              <span className="font-semibold text-ink mt-0.5 block">
                {bridgeStatus?.channels.whatsapp.devices_count || 0} trusted
              </span>
            </div>
          </div>

          {activeBridgePairing?.channel === "whatsapp" && (
            <div className="space-y-3 rounded-md border border-line bg-surface-raised p-4 text-xs">
              <div className="flex items-center justify-between border-b border-line pb-2">
                <span className="font-semibold text-ink">WhatsApp Pairing Token</span>
                <span className="text-[10px] text-mute font-mono-data">Valid for ~10 minutes</span>
              </div>

              <div className="grid gap-2">
                <div className="flex items-center justify-between bg-surface p-2 rounded border border-line">
                  <span className="text-mute font-mono-data">Pairing Code:</span>
                  <div className="flex items-center gap-2 font-mono-data">
                    <code className="text-ember font-bold">{activeBridgePairing.token}</code>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(activeBridgePairing.token || "", "wa-token")}
                      className="p-1 text-mute hover:text-ink"
                    >
                      {copiedToken === "wa-token" ? <FiCheck size={12} className="text-success" /> : <FiCopy size={12} />}
                    </button>
                  </div>
                </div>

                {activeBridgePairing.deep_link && (
                  <div className="flex items-center justify-between bg-surface p-2 rounded border border-line">
                    <span className="text-mute">Instant Deep Link:</span>
                    <a
                      href={activeBridgePairing.deep_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-emerald-400 font-medium hover:underline flex items-center gap-1"
                    >
                      Open WhatsApp <FiExternalLink size={12} />
                    </a>
                  </div>
                )}
              </div>

              <div className="text-[11px] text-mute space-y-1">
                <p className="font-medium text-ink">How to Pair:</p>
                <ol className="list-decimal list-inside space-y-0.5">
                  <li>Send <code>/start {activeBridgePairing.token}</code> to your SAM WhatsApp bot number.</li>
                  <li>SAM will confirm the pairing handshake and register your number as a trusted operator.</li>
                </ol>
              </div>
            </div>
          )}

          <div className="rounded border border-line bg-surface p-3 text-xs space-y-2">
            <h3 className="font-medium text-ink text-xs">Meta Cloud API Webhook Configuration:</h3>
            <p className="text-mute text-[11px]">
              Point your Meta App Webhook Callback URL to this machine:
            </p>
            <div className="flex items-center justify-between bg-surface-raised p-2 rounded border border-line font-mono-data text-[11px]">
              <code className="text-ink">http://&lt;your-host&gt;:8420/api/bridges/whatsapp/webhook</code>
              <button
                type="button"
                onClick={() => copyToClipboard("/api/bridges/whatsapp/webhook", "wa-wh")}
                className="text-mute hover:text-ink"
              >
                {copiedToken === "wa-wh" ? <FiCheck size={12} className="text-success" /> : <FiCopy size={12} />}
              </button>
            </div>
          </div>
        </Card>
      )}

      {/* Tab: Telegram Bot */}
      {activeTab === "telegram" && (
        <Card className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
                <FiSend className="text-sky-400" /> Telegram Companion Bot
              </h2>
              <p className="mt-1 text-xs text-mute">
                Chat with SAM on your phone, receive notifications, and run background agents from Telegram.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleBridgeStatus("telegram", bridgeStatus?.channels.telegram.status || "")}
                loading={busy}
              >
                {bridgeStatus?.channels.telegram.status === "active" ? "Pause Bot" : "Activate Bot"}
              </Button>
              <Button variant="primary" size="sm" onClick={() => pairBridgeChannel("telegram")} loading={busy}>
                <FiSend size={13} /> Pair Telegram
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Bot Status</span>
              <span className="font-semibold text-ink capitalize mt-0.5 block">
                {bridgeStatus?.channels.telegram.status || "ready"}
              </span>
            </div>
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Bot Username</span>
              <span className="font-mono-data text-ink text-[11px] mt-0.5 block">
                @{bridgeStatus?.channels.telegram.bot_username || "sam_companion_bot"}
              </span>
            </div>
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Paired Users</span>
              <span className="font-semibold text-ink mt-0.5 block">
                {bridgeStatus?.channels.telegram.devices_count || 0} trusted
              </span>
            </div>
          </div>

          {activeBridgePairing?.channel === "telegram" && (
            <div className="space-y-3 rounded-md border border-line bg-surface-raised p-4 text-xs">
              <div className="flex items-center justify-between border-b border-line pb-2">
                <span className="font-semibold text-ink">Telegram Pairing Token</span>
                <span className="text-[10px] text-mute font-mono-data">Expires in ~10 mins</span>
              </div>

              <div className="grid gap-2">
                <div className="flex items-center justify-between bg-surface p-2 rounded border border-line">
                  <span className="text-mute font-mono-data">Pairing Token:</span>
                  <div className="flex items-center gap-2 font-mono-data">
                    <code className="text-ember font-bold">{activeBridgePairing.token}</code>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(activeBridgePairing.token || "", "tg-token")}
                      className="p-1 text-mute hover:text-ink"
                    >
                      {copiedToken === "tg-token" ? <FiCheck size={12} className="text-success" /> : <FiCopy size={12} />}
                    </button>
                  </div>
                </div>

                {activeBridgePairing.deep_link && (
                  <div className="flex items-center justify-between bg-surface p-2 rounded border border-line">
                    <span className="text-mute">1-Click Deep Link:</span>
                    <a
                      href={activeBridgePairing.deep_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sky-400 font-medium hover:underline flex items-center gap-1"
                    >
                      Open in Telegram <FiExternalLink size={12} />
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Tab: Apple iOS & Siri */}
      {activeTab === "ios" && (
        <Card className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
                <FiRadio className="text-pink-400" /> Apple iOS & iPhone Siri Companion
              </h2>
              <p className="mt-1 text-xs text-mute">
                Trigger SAM directly via Siri or your iPhone 15/16 Pro Action Button. Returns spoken answers to AirPods and syncs with Apple Continuity.
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={() => pairBridgeChannel("apple_ios")} loading={busy}>
              <FiRadio size={13} /> Generate Shortcut Setup
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Execution Engine</span>
              <span className="font-semibold text-emerald-400 mt-0.5 block">Sub-ms Tier 1 Bypass</span>
            </div>
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Voice Audio</span>
              <span className="font-semibold text-ink mt-0.5 block">AirPods WAV Synthesis</span>
            </div>
            <div className="p-3 rounded border border-line bg-surface-raised">
              <span className="text-[11px] text-mute block">Continuity Services</span>
              <span className="font-semibold text-ink mt-0.5 block">Safari, Notes, Reminders</span>
            </div>
          </div>

          {activeBridgePairing?.channel === "apple_ios" && activeBridgePairing.shortcut_def && (
            <div className="space-y-3 rounded-md border border-line bg-surface-raised p-4 text-xs">
              <div className="flex items-center justify-between border-b border-line pb-2">
                <span className="font-semibold text-ink">Ready-to-Import iOS Shortcut Payload</span>
                <span className="text-[10px] text-mute font-mono-data">Action Button & Siri Ready</span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between bg-surface p-2 rounded border border-line font-mono-data text-[11px]">
                  <span className="text-mute">API Endpoint:</span>
                  <code className="text-ink">{String(activeBridgePairing.shortcut_def.endpoint)}</code>
                </div>

                <div className="bg-surface p-2.5 rounded border border-line text-[11px] space-y-1 text-mute">
                  <p className="font-medium text-ink">30-Second Setup in iOS Shortcuts App:</p>
                  <ol className="list-decimal list-inside space-y-1">
                    {Array.isArray(activeBridgePairing.shortcut_def.instructions) &&
                      activeBridgePairing.shortcut_def.instructions.map((step: string, i: number) => (
                        <li key={i}>{step}</li>
                      ))}
                  </ol>
                </div>
              </div>
            </div>
          )}

          <div className="rounded border border-line bg-surface p-3 text-xs space-y-2">
            <h3 className="font-medium text-ink text-xs flex items-center gap-1.5">
              <FiCompass className="text-pink-400" /> Apple Continuity & Handoff Integration:
            </h3>
            <p className="text-mute text-[11px]">
              When you ask SAM from iPhone ("Save to my notes" or "What tab is open on my Mac?"), SAM uses native macOS AppleScript to bridge Safari tabs, Apple Notes, and Reminders into your iCloud stream.
            </p>
          </div>
        </Card>
      )}

      {/* Tab: Wi-Fi Pairing */}
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
                <span className="text-[10px] text-mute font-mono-data">Expires in ~10 mins</span>
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
                      onClick={() => copyToClipboard(pairing.token, "wifi-token")}
                      className="p-1 text-mute hover:text-ink"
                    >
                      {copiedToken === "wifi-token" ? <FiCheck size={12} className="text-success" /> : <FiCopy size={12} />}
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
        </Card>
      )}

      {/* Tab: USB Cable */}
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
                    onClick={() => copyToClipboard("adb reverse tcp:8420 tcp:8420", "adb-cmd")}
                    className="text-mute hover:text-ink"
                  >
                    {copiedToken === "adb-cmd" ? <FiCheck size={12} className="text-success" /> : <FiCopy size={12} />}
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
        </Card>
      )}

      {/* Tab: Troubleshooting Guide */}
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
          </div>
        </Card>
      )}

      {/* Omnichannel Broadcast Dispatch */}
      <Card className="space-y-3">
        <h2 className="font-semibold text-ink text-sm flex items-center gap-1.5">
          <FiRadio className="text-ember" /> Omnichannel Broadcast
        </h2>
        <p className="text-xs text-mute">
          Send an announcement simultaneously across all active channels (Desktop, Mobile, Telegram, and WhatsApp).
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            className="flex-1 rounded-md border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:outline-none"
            placeholder="Broadcast announcement text..."
            value={broadcastText}
            onChange={(e) => setBroadcastText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && broadcastAll()}
          />
          <Button variant="primary" size="sm" onClick={broadcastAll} loading={busy} disabled={!broadcastText.trim()}>
            Broadcast All
          </Button>
        </div>
      </Card>

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
            No devices paired yet. Select any channel above to pair your device.
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
