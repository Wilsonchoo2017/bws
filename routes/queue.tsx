import { Head } from "$fresh/runtime.ts";
import QueueDiagnosticsDashboard from "../islands/QueueDiagnosticsDashboard.tsx";

export default function QueuePage() {
  return (
    <>
      <Head>
        <title>Queue Diagnostics - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          {/* Header */}
          <div class="mb-6">
            <div class="text-sm breadcrumbs">
              <ul>
                <li><a href="/">Home</a></li>
                <li>Queue Diagnostics</li>
              </ul>
            </div>
            <h1 class="text-3xl lg:text-4xl font-bold text-base-content mt-2">
              Queue Diagnostics
            </h1>
            <p class="text-base-content/70 mt-2">
              Comprehensive monitoring and diagnostics for the scraping queue
              system
            </p>
          </div>

          {/* Dashboard */}
          <QueueDiagnosticsDashboard />
        </div>
      </div>
    </>
  );
}
