import { useEffect, type JSX, type ReactNode } from "react";
import { createBrowserRouter, useLocation, useNavigate } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { FeatureStubPage } from "@/features/FeatureStubPage";
import { DesignSystemPage } from "@/features/dev/DesignSystemPage";
import { IqooPage } from "@/features/iqoo/IqooPage";
import { CommandCenterPage } from "@/features/command-center/CommandCenterPage";
import { ChatPage } from "@/features/chat/ChatPage";
import { MemoryPage } from "@/features/memory/MemoryPage";
import { FounderModePage } from "@/features/founder-mode/FounderModePage";
import { SkillsPage } from "@/features/skills/SkillsPage";
import { BrainPage } from "@/features/brain/BrainPage";
import { HandsPage } from "@/features/hands/HandsPage";
import { TasksPage } from "@/features/tasks/TasksPage";
import { DiagnosticsPage } from "@/features/diagnostics/DiagnosticsPage";
import { LicensingPage } from "@/features/licensing/LicensingPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { PermissionsPage } from "@/features/permissions/PermissionsPage";
import { ROUTES } from "./routes";
import { useRuntime } from "@/stores/runtime";
import { isNative } from "@/lib/native";

function FirstRunRedirect({ children }: { children: ReactNode }) {
  const { setupState } = useRuntime();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (isNative() && setupState?.state === "first_run" && location.pathname !== "/onboarding") {
      navigate("/onboarding", { replace: true });
    }
  }, [setupState, location.pathname, navigate]);
  return children;
}

// Routes that have a built page component, per PHASE5_PLAN.md §H — real
// data or demo data, either way, rather than the shared placeholder stub.
// Renamed from an earlier REAL_PAGES: that name stopped being accurate the
// moment the first demo page (Chat) joined it — whether a page's *data* is
// real or demo is what ModeBadge communicates, this map is just "built or
// not". Everything not listed here still renders FeatureStubPage.
const BUILT_PAGES: Partial<Record<string, () => JSX.Element>> = {
  "/": CommandCenterPage,
  "/iqoo": IqooPage,
  "/chat": ChatPage,
  "/tasks": TasksPage,
  "/brain": BrainPage,
  "/hands": HandsPage,
  "/memory": MemoryPage,
  "/founder-mode": FounderModePage,
  "/skills": SkillsPage,
  "/diagnostics": DiagnosticsPage,
  "/licensing": LicensingPage,
  "/settings": SettingsPage,
  "/permissions": PermissionsPage,
};

export const router = createBrowserRouter([
  // Standalone, outside AppShell on purpose — no sidebar/topbar chrome for
  // a first-run wizard. The native app redirects fresh installs here using
  // the persisted setup journey; browser previews remain directly navigable.
  { path: "/onboarding", element: <OnboardingPage /> },
  {
    element: <FirstRunRedirect><AppShell /></FirstRunRedirect>,
    children: [
      ...ROUTES.map((route) => {
        const Page = BUILT_PAGES[route.path];
        return {
          path: route.path,
          element: Page ? <Page /> : <FeatureStubPage />,
        };
      }),
      { path: "/_dev/design-system", element: <DesignSystemPage /> },
    ],
  },
]);
