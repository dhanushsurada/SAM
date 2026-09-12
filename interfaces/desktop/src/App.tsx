import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@/app/theme";
import { TaskSessionProvider } from "@/stores/taskSession";
import { router } from "@/app/router";

export function App() {
  return (
    <ThemeProvider>
      <TaskSessionProvider>
        <RouterProvider router={router} />
      </TaskSessionProvider>
    </ThemeProvider>
  );
}
