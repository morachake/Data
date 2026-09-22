// observablehq.config.js — African Football Data dashboard configuration
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default {
  root: "src",
  title: "African Football Data",
  theme: "dashboard",
  search: true,
  toc: false,
  // Python loaders run inside the repo .venv
  interpreters: {
    ".py": [resolve(__dirname, "../.venv/bin/python3")]
  },
  pages: [
    { name: "Overview",  path: "/" },
    { name: "Leagues",   path: "/league" },
    { name: "Shortlist", path: "/shortlist" },
    { name: "Players",   path: "/players" },
    { name: "Coverage",  path: "/coverage" }
  ],
  footer: "African Football Data Platform · SA Premiership · Egyptian PL · Botola Pro · Tanzania PL · Kenya PL · CAF"
};
