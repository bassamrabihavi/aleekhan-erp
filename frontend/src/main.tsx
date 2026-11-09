import "vazirmatn/Vazirmatn-Variable-font-face.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/app.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { createQueryClient } from "./queryClient";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing in index.html");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
