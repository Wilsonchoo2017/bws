import { type PageProps } from "$fresh/server.ts";
import Sidebar from "../islands/Sidebar.tsx";

export default function App({ Component, url }: PageProps) {
  return (
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>LEGO Price Tracker</title>
        <link rel="stylesheet" href="/styles.css" />
      </head>
      <body>
        <div class="drawer lg:drawer-open">
          <input id="main-drawer" type="checkbox" class="drawer-toggle" />

          {/* Main content */}
          <div class="drawer-content flex flex-col bg-base-200">
            {/* Navbar for mobile */}
            <div class="w-full navbar bg-base-100 lg:hidden sticky top-0 z-30 shadow-md">
              <div class="flex-none">
                <label for="main-drawer" class="btn btn-square btn-ghost">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="inline-block w-6 h-6 stroke-current">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path>
                  </svg>
                </label>
              </div>
              <div class="flex-1">
                <span class="text-xl font-bold">LEGO Tracker</span>
              </div>
            </div>

            {/* Page content */}
            <main class="flex-1">
              <Component />
            </main>
          </div>

          {/* Sidebar */}
          <div class="drawer-side z-40">
            <label for="main-drawer" aria-label="close sidebar" class="drawer-overlay"></label>
            <aside class="bg-base-100 w-64 min-h-full">
              <Sidebar currentPath={url.pathname} />
            </aside>
          </div>
        </div>
      </body>
    </html>
  );
}
