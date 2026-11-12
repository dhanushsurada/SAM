import { useState } from "react";
import { FiKey } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

export function LicensingPage() {
  const [activated, setActivated] = useState(true);

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <PageHeader
        title="Licensing"
        mode="live"
        description="SAM is fully sovereign and local-first: no cloud account required. Running on local device license."
      />

      <Card className="space-y-3">
        <div className="flex items-center gap-2.5">
          <FiKey size={16} className="text-mute" />
          <span className="text-sm text-ink">Activation</span>
          <StatusPill state={activated ? "SUCCESS" : "WAITING"} label={activated ? "Active" : "Not activated"} />
        </div>
        <p className="font-mono-data text-xs text-mute">tier: sovereign_personal · offline hardware verified</p>
        <Button variant="secondary" size="sm" onClick={() => setActivated((a) => !a)}>
          {activated ? "Deactivate (demo)" : "Activate (demo)"}
        </Button>
      </Card>
    </div>
  );
}
