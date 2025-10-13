import { useCallback, useMemo, useState } from "react";
import { Activity, RefreshCw } from 'lucide-react';
import type { Socket } from 'socket.io-client';
import MotorCard from '../components/MotorCard';
import { useSocketConnection } from '../hooks/useSocketConnection';
import { PageHeader } from '../components/layout/PageHeader';
import { ConnectionIndicator } from '../components/ui/ConnectionIndicator';
import { AlertBanner } from '../components/ui/AlertBanner';
import { LoadingState } from '../components/ui/LoadingState';
import { MotorCardPlaceholder } from '../components/MotorCardPlaceholder';

interface MotorStatus {
  state: string;
  q: number[];
  error: any[];
  limits: any[];
}

export default function MotorStatusPage() {
  const [status, setStatus] = useState<MotorStatus | null>(null);
  const [initialTelemetryReceived, setInitialTelemetryReceived] = useState(false);

  const handleTelemetry = useCallback((data: MotorStatus) => {
    setStatus(data);
    setInitialTelemetryReceived(true);
  }, []);

  const { status: connectionStatus, reconnect } = useSocketConnection('http://localhost:5000', {
    registerHandlers: useCallback((socket: Socket) => {
      socket.on('telemetry', handleTelemetry);
      return () => socket.off('telemetry', handleTelemetry);
    }, [handleTelemetry]),
    onDisconnect: () => {
      setInitialTelemetryReceived(false);
    },
    onConnectError: (_error) => {
      void _error;
      return 'Failed to connect to backend server. Please ensure the backend is running.';
    },
  });

  const { connected, loading: connecting, reconnecting, error } = connectionStatus;

  const loadingMessage = connecting
    ? 'Connecting to motors...'
    : 'Waiting for telemetry...';

  const showLoading = connecting || (connected && !initialTelemetryReceived);

  const isEnabled = status ? ['RUNNING', 'EXECUTING'].includes(status.state) : false;

  const limits = useMemo(() => status?.limits ?? [], [status]);
  const errors = useMemo(() => status?.error ?? [], [status]);

  return (
    <section className="py-8 min-h-screen">
      <div className="max-w-6xl mx-auto px-6">
        <PageHeader
          title="Motor Status Dashboard"
          description="Real-time monitoring of robotic arm joint positions, status indicators, and limit switches"
          centered
          statusSlot={<ConnectionIndicator connected={connected} />}
        />

  {showLoading && <LoadingState message={loadingMessage} className="py-24" />}

        {error && (
          <AlertBanner
            variant="error"
            title="Connection Error"
            message={error}
            action={{
              label: reconnecting ? 'Reconnecting...' : 'Retry Connection',
              onClick: reconnect,
              icon: <RefreshCw className="w-4 h-4" />,
              loading: reconnecting,
            }}
            className="mb-8"
          />
        )}

        {!connected && !error && !connecting && (
          <AlertBanner
            variant="warning"
            title="Connection Required"
            message="Attempting to connect to backend server..."
            className="mb-8"
          />
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
              const limit = limits[idx] || [false, false];
              const topLimitHit = limit[0] || false;
              const bottomLimitHit = limit[1] || false;
              const encoderError = errors[idx] || 0;
              
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
        ) : !showLoading && (
          // Show placeholder cards when disconnected
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, idx) => (
              <MotorCardPlaceholder key={idx} index={idx} />
            ))}
          </div>
        )}

      </div>
    </section>
  );
}
