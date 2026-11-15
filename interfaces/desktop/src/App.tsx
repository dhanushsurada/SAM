import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@/app/theme";
import { ProfileProvider } from "@/features/profile/ProfileContext";
import { TaskSessionProvider } from "@/stores/taskSession";
import { RuntimeProvider } from "@/stores/runtime";
import { VoiceProvider } from "@/features/voice/VoiceProvider";
import { router } from "@/app/router";

export function App() {
  return (
    <ThemeProvider>
      <ProfileProvider>
        <RuntimeProvider>
          <TaskSessionProvider>
            <VoiceProvider>
              <RouterProvider router={router} />
            </VoiceProvider>
          </TaskSessionProvider>
        </RuntimeProvider>
      </ProfileProvider>
    </ThemeProvider>
  );
}
