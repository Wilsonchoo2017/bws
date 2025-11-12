interface SidebarProps {
  currentPath: string;
}

interface NavItem {
  name: string;
  path: string;
  icon: string;
}

const navItems: NavItem[] = [
  {
    name: "Home",
    path: "/",
    icon:
      `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />`,
  },
  {
    name: "Products",
    path: "/products",
    icon:
      `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />`,
  },
];

export default function Sidebar({ currentPath }: SidebarProps) {
  const isActivePath = (path: string): boolean => {
    if (path === "/") {
      return currentPath === "/";
    }
    return currentPath.startsWith(path);
  };

  const SidebarContent = () => (
    <div class="flex flex-col h-full">
      {/* Logo/Brand */}
      <div class="p-6 border-b border-base-300">
        <h2 class="text-2xl font-bold text-primary">LEGO Tracker</h2>
        <p class="text-sm text-base-content/60 mt-1">Price Monitoring</p>
      </div>

      {/* Navigation */}
      <nav class="flex-1 p-4 space-y-2 overflow-y-auto">
        <ul class="menu menu-lg">
          {navItems.map((item) => (
            <li key={item.path}>
              <a
                href={item.path}
                class={isActivePath(item.path) ? "active" : ""}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  dangerouslySetInnerHTML={{ __html: item.icon }}
                />
                {item.name}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div class="p-4 border-t border-base-300">
        <div class="text-xs text-base-content/50 text-center">
          <p>LEGO Price Tracker v1.0</p>
          <p class="mt-1">Built with Fresh & Deno</p>
        </div>
      </div>
    </div>
  );

  return <SidebarContent />;
}
