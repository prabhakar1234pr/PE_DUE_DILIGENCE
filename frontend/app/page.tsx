async function getBackendHealth() {
  try {
    const response = await fetch("http://localhost:8000/api/health", {
      cache: "no-store",
    });
    if (!response.ok) {
      return { status: "error", service: "backend-unreachable" };
    }
    return response.json() as Promise<{ status: string; service: string }>;
  } catch {
    return { status: "error", service: "backend-unreachable" };
  }
}

export default async function Home() {
  const health = await getBackendHealth();

  return (
    <main className="min-h-screen p-10">
      <h1 className="text-3xl font-bold">Next.js Frontend Connected to FastAPI</h1>
      <p className="mt-4 text-lg">Backend status: {health.status}</p>
      <p className="text-lg">Backend service: {health.service}</p>
      <p className="mt-6 text-sm text-gray-600">
        Endpoint used: http://localhost:8000/api/health
      </p>
    </main>
  );
}
