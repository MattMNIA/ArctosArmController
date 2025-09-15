import { useEffect, useState } from "react";

interface MotorStatus {
  state: string;
  q: number[];
  error: any[];
  limits: any[];
  mode: string;
}

export default function MotorStatusPage() {
  const [status, setStatus] = useState<MotorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchStatus() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/status");
        if (!res.ok) throw new Error("Failed to fetch status");
        const data = await res.json();
        setStatus(data);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchStatus();
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Motor Status</h1>
      {loading && <div>Loading...</div>}
      {error && <div className="text-red-500">{error}</div>}
      {status && (
        <div className="space-y-4">
          <div>
            <span className="font-semibold">System State:</span> {status.state}
          </div>
          <div>
            <span className="font-semibold">Mode:</span> {status.mode}
          </div>
          <div>
            <span className="font-semibold">Joint Positions (q):</span>
            <ul className="list-disc ml-6">
              {status.q.map((val, idx) => (
                <li key={idx}>
                  <span className="font-semibold">Motor {idx + 1}:</span> {val.toFixed(3)}
                </li>
              ))}
            </ul>
          </div>
          {status.error && status.error.length > 0 && (
            <div>
              <span className="font-semibold text-red-600">Errors:</span>
              <ul className="list-disc ml-6 text-red-600">
                {status.error.map((err, idx) => (
                  <li key={idx}>{JSON.stringify(err)}</li>
                ))}
              </ul>
            </div>
          )}
          {status.limits && status.limits.length > 0 && (
            <div>
              <span className="font-semibold text-yellow-600">Limits:</span>
              <ul className="list-disc ml-6 text-yellow-600">
                {status.limits.map((lim, idx) => (
                  <li key={idx}>{JSON.stringify(lim)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
