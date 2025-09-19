import { useState, useEffect } from 'react';
import { RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';

export default function SimulationVideo() {
  const [simulationActive, setSimulationActive] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const checkSimulationStatus = async () => {
    setLoading(true);
    setError(null);
    setRetrying(true);

    try {
      const response = await fetch('http://localhost:5000/api/sim/status');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();
      setSimulationActive(data.simulation_active);
    } catch (error) {
      console.error('Error checking simulation status:', error);
      setError(error instanceof Error ? error.message : 'Failed to check simulation status');
      setSimulationActive(false);
    } finally {
      setLoading(false);
      setRetrying(false);
    }
  };

  useEffect(() => {
    checkSimulationStatus();
  }, []);

  const handleRefresh = () => {
    checkSimulationStatus();
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center space-x-3">
          <div className="w-6 h-6 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-xl text-gray-300">
            {retrying ? 'Checking simulation status...' : 'Loading simulation status...'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <section className="py-8 min-h-screen">
      <div className="max-w-4xl mx-auto px-4">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">PyBullet Simulation Video Feed</h1>
          <button
            onClick={handleRefresh}
            disabled={retrying}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg font-semibold transition-colors duration-200 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-4 h-4 ${retrying ? 'animate-spin' : ''}`} />
            <span>{retrying ? 'Checking...' : 'Refresh'}</span>
          </button>
        </div>

        {/* Status Indicator */}
        <div className="mb-6 flex items-center justify-center space-x-2">
          {simulationActive ? (
            <>
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-sm font-semibold text-green-400">
                Simulation Active
              </span>
            </>
          ) : (
            <>
              <AlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-sm font-semibold text-red-400">
                Simulation Inactive
              </span>
            </>
          )}
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-2xl p-4 mb-6">
            <div className="flex items-center space-x-3">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <div>
                <h3 className="font-semibold text-red-400">Connection Error</h3>
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            </div>
          </div>
        )}
        
        {simulationActive ? (
          <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4">
            <h2 className="text-xl font-semibold mb-4">Live Simulation Feed</h2>
            <img 
              src="http://localhost:5000/api/sim/video_feed" 
              alt="PyBullet Simulation" 
              className="w-full max-w-2xl mx-auto border rounded"
              onError={() => setSimulationActive(false)}
            />
          </div>
        ) : (
          <div className="bg-red-100 dark:bg-red-900 rounded-lg p-8 text-center">
            <h2 className="text-xl font-semibold mb-4 text-red-800 dark:text-red-200">Simulation Not Running</h2>
            <p className="text-red-600 dark:text-red-300 mb-4">
              The PyBullet simulation is not currently active. Please start the backend with the PyBullet driver to view the video feed.
            </p>
            <button
              onClick={handleRefresh}
              disabled={retrying}
              className="flex items-center space-x-2 px-6 py-3 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg font-semibold transition-colors duration-200 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-4 h-4 ${retrying ? 'animate-spin' : ''}`} />
              <span>{retrying ? 'Checking...' : 'Check Again'}</span>
            </button>
          </div>
        )}
      </div>
    </section>
  );
}