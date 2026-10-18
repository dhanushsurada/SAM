import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@/app/theme";
import { TaskSessionProvider } from "@/stores/taskSession";
import { RuntimeProvider } from "@/stores/runtime";
import { router } from "@/app/router";

export function App() {
  return (
    <ThemeProvider>
      <RuntimeProvider>
        <TaskSessionProvider>
          <RouterProvider router={router} />
        </TaskSessionProvider>
      </RuntimeProvider>
    </ThemeProvider>
  );
}
