export default function Home() {
  return (
    <div class="min-h-screen bg-base-200">
      <div class="container mx-auto px-4 py-16">
        <div class="text-center mb-12">
          <h1 class="text-5xl font-bold mb-4">Fresh + DaisyUI</h1>
          <p class="text-xl text-base-content/70">
            Deno Fresh with DaisyUI component library
          </p>
        </div>

        <div class="grid gap-8 max-w-4xl mx-auto">
          {/* Buttons */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title">Buttons</h2>
              <div class="flex flex-wrap gap-2">
                <button class="btn">Default</button>
                <button class="btn btn-primary">Primary</button>
                <button class="btn btn-secondary">Secondary</button>
                <button class="btn btn-accent">Accent</button>
                <button class="btn btn-info">Info</button>
                <button class="btn btn-success">Success</button>
                <button class="btn btn-warning">Warning</button>
                <button class="btn btn-error">Error</button>
              </div>
            </div>
          </div>

          {/* Forms */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title">Form Elements</h2>
              <div class="form-control w-full max-w-xs">
                <label class="label">
                  <span class="label-text">Email</span>
                </label>
                <input
                  type="text"
                  placeholder="Type here"
                  class="input input-bordered w-full max-w-xs"
                />
              </div>
              <div class="form-control">
                <label class="label cursor-pointer">
                  <span class="label-text">Remember me</span>
                  <input type="checkbox" checked class="checkbox" />
                </label>
              </div>
            </div>
          </div>

          {/* Alert */}
          <div class="alert alert-info">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              class="stroke-current shrink-0 w-6 h-6"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>DaisyUI is successfully integrated!</span>
          </div>

          {/* Badge */}
          <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
              <h2 class="card-title">Badges</h2>
              <div class="flex flex-wrap gap-2">
                <div class="badge">neutral</div>
                <div class="badge badge-primary">primary</div>
                <div class="badge badge-secondary">secondary</div>
                <div class="badge badge-accent">accent</div>
                <div class="badge badge-ghost">ghost</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
