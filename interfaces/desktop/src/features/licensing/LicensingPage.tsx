import { useState } from "react";
import { FiKey } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { Button } from "@/components/Button";

export function LicensingPage() {
  const [activated, setActivated] = useState(true);

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <PageHeader
        title="Licensing"
        mode="demo"
        description="LicenseManager.check()/install_license() exist internally, nothing exposes them over HTTP yet. Local-first: no cloud account, ever."
      />

      <div className="space-y-3 rounded-lg border border-line bg-surface p-4 shadow-panel">
        <div className="flex items-center gap-2.5">
          <FiKey size={16} className="text-mute" />
          <span className="text-sm text-ink">Activation</span>
          <StatusPill state={activated ? "SUCCESS" : "WAITING"} label={activated ? "Active" : "Not activated"} />
        </div>
        <p className="font-mono-data text-xs text-mute">tier: hackathon · local verification only</p>
        <Button variant="secondary" size="sm" onClick={() => setActivated((a) => !a)}>
          {activated ? "Deactivate (demo)" : "Activate (demo)"}
        </Button>
      </div>
    </div>
  );
}
