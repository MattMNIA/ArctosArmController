import { useEffect, useState, useRef } from "react";
import { Activity, AlertCircle, Wifi, WifiOff, RefreshCw } from 'lucide-react';
import io, { Socket } from 'socket.io-client';
import MotorCard from '../components/MotorCard';

interface MotorStatus {
  state: string;
  q: number[];
  error: any[];
  limits: any[];
}

export default function MotorStatusPage() {
  const [status, setStatus] = useState<MotorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  const connectToSocket = () => {
    // Disconnect existing socket if any
    if (socketRef.current) {
      socketRef.current.disconnect();
    }

    setLoading(true);
    setReconnecting(true);
    setError(null);

    const socket = io('http://localhost:5000', {
      transports: ['websocket', 'polling'],
      timeout: 5000,
      forceNew: true
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      setLoading(false);
      setReconnecting(false);
      setError(null);
      setConnected(true);
    });

    socket.on('disconnect', (reason) => {
      setError(`Disconnected from server: ${reason}`);
      setConnected(false);
      setLoading(false);
      setReconnecting(false);
    });

    socket.on('telemetry', (data: MotorStatus) => {
      setStatus(data);
      setLoading(false);
    });

    socket.on('connect_error', (err) => {
      setError('Failed to connect to backend server. Please ensure the backend is running.');
      setLoading(false);
      setConnected(false);
      setReconnecting(false);
    });

    // Set a timeout for connection attempt
    setTimeout(() => {
      if (!socket.connected) {
        setError('Connection timeout. Backend server may not be running.');
        setLoading(false);
        setReconnecting(false);
      }
    }, 10000);
  };

  useEffect(() => {
    connectToSocket();

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  const isEnabled = status ? ['RUNNING', 'EXECUTING'].includes(status.state) : false;

  return (
    <section className="py-8 min-h-screen">
      <div className="max-w-6xl mx-auto px-6">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-3xl md:text-4xl font-bold mb-4">
            <span className="text-white">
              Motor Status Dashboard
            </span>
          </h1>
          <div className="h-1 w-20 bg-blue-500 mx-auto mb-6 rounded-full"></div>
          
          {/* Connection Status */}
          <div className="flex items-center justify-center space-x-2 mb-6">
            {connected ? (
              <>
                <Wifi className="w-5 h-5 text-green-400" />
                <span className="text-sm font-semibold text-green-400">
                  Connected
                </span>
              </>
            ) : (
              <>
                <WifiOff className="w-5 h-5 text-red-400" />
                <span className="text-sm font-semibold text-red-400">
                  Disconnected
                </span>
              </>
            )}
          </div>

          <p className="text-lg text-gray-300 max-w-2xl mx-auto">
            Real-time monitoring of robotic arm joint positions, status indicators, and limit switches
          </p>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-24">
            <div
              className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"
            />
            <span className="ml-4 text-gray-400">Connecting to motors...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-2xl p-6 mb-8">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <AlertCircle className="w-6 h-6 text-red-400" />
                <div>
                  <h3 className="font-semibold text-red-400">Connection Error</h3>
                  <p className="text-red-300">{error}</p>
                </div>
              </div>
              <button
                onClick={connectToSocket}
                disabled={reconnecting}
                className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg font-semibold transition-colors duration-200 disabled:cursor-not-allowed"
              >
                <RefreshCw className="w-4 h-4" />
                <span>{reconnecting ? 'Reconnecting...' : 'Retry Connection'}</span>
              </button>
            </div>
          </div>
        )}

        {/* System Status Bar */}
        {status && (
          <div className="bg-gray-800 rounded-2xl p-6 mb-8 border border-gray-700 shadow-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <Activity className="w-6 h-6 text-blue-400" />
                <div>
                  <h3 className="font-semibold text-white">System State</h3>
                  <p className="text-sm text-gray-400">Overall robot status</p>
                </div>
              </div>
              <div className="text-right">
                <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${
                  isEnabled
                    ? 'bg-green-900/30 text-green-400'
                    : 'bg-gray-700 text-gray-400'
                }`}>
                  {status.state}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Motor Cards Grid */}
        {connected && status && status.q ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {status.q.map((position, idx) => {
              const limit = status.limits?.[idx] || [false, false];
              const topLimitHit = limit[0] || false;
              const bottomLimitHit = limit[1] || false;
              const encoderError = status.error?.[idx] || 0;
              
              return (
                <MotorCard
                  key={idx}
                  motorIndex={idx}
                  position={position}
                  isEnabled={isEnabled}
                  topLimitHit={topLimitHit}
                  bottomLimitHit={bottomLimitHit}
                  encoderError={encoderError}
                />
              );
            })}
          </div>
        ) : !loading && (
          // Show placeholder cards when disconnected
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, idx) => (
              <div
                key={idx}
                className="relative bg-gray-800/50 rounded-3xl border-2 border-dashed border-gray-600 p-8 opacity-50"
              >
                {/* Overlay indicating disconnection */}
                <div className="absolute inset-0 bg-gray-900/80 rounded-3xl flex items-center justify-center">
                  <div className="text-center">
                    <WifiOff className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                    <p className="text-sm font-semibold text-gray-400">
                      Motor {idx + 1}
                    </p>
                    <p className="text-xs text-gray-500">
                      Disconnected
                    </p>
                  </div>
                </div>

                {/* Placeholder card structure (dimmed) */}
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 bg-gray-600 rounded-2xl flex items-center justify-center">
                      <span className="text-gray-400 font-bold text-sm">
                        {idx + 1}
                      </span>
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-gray-500">
                        Motor {idx + 1}
                      </h3>
                      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">
                        Joint Controller
                      </p>
                    </div>
                  </div>
                  <div className="w-4 h-4 rounded-full bg-gray-600" />
                </div>

                <div className="bg-gray-700 rounded-2xl p-4 mb-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold text-gray-500 mb-1">Position</p>
                      <div className="text-3xl font-black text-gray-500">
                        --°
                      </div>
                    </div>
                    <div className="w-12 h-12 bg-gray-600 rounded-xl" />
                  </div>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-semibold text-gray-500">Limit Switches</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-700 rounded-xl p-3">
                      <div className="flex items-center space-x-3">
                        <div className="w-5 h-5 rounded-full bg-gray-600" />
                        <div>
                          <p className="text-sm font-semibold text-gray-500">Top</p>
                          <p className="text-xs font-medium text-gray-500">--</p>
                        </div>
                      </div>
                    </div>
                    <div className="bg-gray-700 rounded-xl p-3">
                      <div className="flex items-center space-x-3">
                        <div className="w-5 h-5 rounded-full bg-gray-600" />
                        <div>
                          <p className="text-sm font-semibold text-gray-500">Bottom</p>
                          <p className="text-xs font-medium text-gray-500">--</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

      </div>
    </section>
  );
}
