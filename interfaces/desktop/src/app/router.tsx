import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { FeatureStubPage } from "@/features/FeatureStubPage";
import { DesignSystemPage } from "@/features/dev/DesignSystemPage";
import { IqooPage } from "@/features/iqoo/IqooPage";
import { CommandCenterPage } from "@/features/command-center/CommandCenterPage";
import { ChatPage } from "@/features/chat/ChatPage";
import { MemoryPage } from "@/features/memory/MemoryPage";
import { FounderModePage } from "@/features/founder-mode/FounderModePage";
import { SkillsPage } from "@/features/skills/SkillsPage";
import { ModelsPage } from "@/features/models/ModelsPage";
import { DiagnosticsPage } from "@/features/diagnostics/DiagnosticsPage";
import { LicensingPage } from "@/features/licensing/LicensingPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { ROUTES } from "./routes";

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
  "/memory": MemoryPage,
  "/founder-mode": FounderModePage,
  "/skills": SkillsPage,
  "/models": ModelsPage,
  "/diagnostics": DiagnosticsPage,
  "/licensing": LicensingPage,
  "/settings": SettingsPage,
};

export const router = createBrowserRouter([
  // Standalone, outside AppShell on purpose — no sidebar/topbar chrome for
  // a first-run wizard. No auto-redirect into this route: that would need
  // a persisted "has onboarded" flag, and getting that wrong (looping,
  // trapping a returning user) is worse than just leaving it reachable
  // from Sidebar for now.
  { path: "/onboarding", element: <OnboardingPage /> },
  {
    element: <AppShell />,
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
