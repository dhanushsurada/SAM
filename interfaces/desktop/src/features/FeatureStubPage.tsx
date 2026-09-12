import { useLocation } from "react-router-dom";
import { findRoute } from "@/app/routes";
import { EmptyState } from "@/components/EmptyState";

/**
 * Every route in ROUTES points here today. As each feature gets its real
 * build (per PHASE5_PLAN.md §H), that route's `element` in router.tsx swaps
 * from <FeatureStubPage /> to the real page component — this file doesn't
 * change, routes just stop pointing at it one at a time.
 */
export function FeatureStubPage() {
  const location = useLocation();
  const route = findRoute(location.pathname);

  if (!route) {
    return (
      <EmptyState
        icon={findRoute("/")!.icon}
        title="Not found"
        description="No route matches this path."
      />
    );
  }

  return (
    <EmptyState
      icon={route.icon}
      title={route.label}
      description={route.description}
      mode="planned"
      meta={`${route.plannedStep} — see docs/frontend/PHASE5_PLAN.md §H`}
    />
  );
}
