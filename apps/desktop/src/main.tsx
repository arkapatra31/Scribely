import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// macOS draws the traffic lights over our content (overlay title bar); the sidebar makes room.
if (/Mac/.test(navigator.userAgent)) document.documentElement.classList.add("platform-mac");

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing from index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
