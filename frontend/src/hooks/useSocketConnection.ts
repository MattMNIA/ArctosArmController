import { useCallback, useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';
import type { ManagerOptions, SocketOptions, Socket } from 'socket.io-client';

interface SocketStatus {
  connected: boolean;
  loading: boolean;
  reconnecting: boolean;
  error: string | null;
}

const defaultStatus: SocketStatus = {
  connected: false,
  loading: false,
  reconnecting: false,
  error: null,
};

interface UseSocketConnectionOptions {
  autoConnect?: boolean;
  socketOptions?: Partial<ManagerOptions & SocketOptions>;
  registerHandlers?: (socket: Socket) => void | (() => void);
  connectionTimeoutMs?: number;
  timeoutMessage?: string;
  onConnect?: (socket: Socket) => void;
  onDisconnect?: (reason: string, socket: Socket) => void;
  onConnectError?: (error: Error, socket: Socket) => string | void;
}

export function useSocketConnection(
  url: string,
  {
    autoConnect = true,
    socketOptions,
    registerHandlers,
    connectionTimeoutMs = 10000,
    timeoutMessage = 'Connection timeout. Backend server may not be running.',
    onConnect,
    onDisconnect,
    onConnectError,
  }: UseSocketConnectionOptions = {}
) {
  const socketRef = useRef<Socket | null>(null);
  const handlersCleanupRef = useRef<(() => void) | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const registerHandlersRef = useRef(registerHandlers);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onConnectErrorRef = useRef(onConnectError);
  const socketOptionsRef = useRef(socketOptions);

  useEffect(() => {
    registerHandlersRef.current = registerHandlers;
  }, [registerHandlers]);

  useEffect(() => {
    onConnectRef.current = onConnect;
  }, [onConnect]);

  useEffect(() => {
    onDisconnectRef.current = onDisconnect;
  }, [onDisconnect]);

  useEffect(() => {
    onConnectErrorRef.current = onConnectError;
  }, [onConnectError]);

  useEffect(() => {
    socketOptionsRef.current = socketOptions;
  }, [socketOptions]);

  const [status, setStatus] = useState<SocketStatus>({
    ...defaultStatus,
    loading: autoConnect,
  });

  const clearTimeoutRef = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const teardownSocket = useCallback(() => {
    handlersCleanupRef.current?.();
    handlersCleanupRef.current = null;

    if (socketRef.current) {
      socketRef.current.off('connect');
      socketRef.current.off('disconnect');
      socketRef.current.off('connect_error');
      socketRef.current.disconnect();
      socketRef.current = null;
    }

    clearTimeoutRef();
  }, [clearTimeoutRef]);

  const connect = useCallback(() => {
    teardownSocket();

    setStatus((prev) => ({
      connected: false,
      loading: true,
      reconnecting: prev.connected || prev.reconnecting,
      error: null,
    }));

    const socket = io(url, {
      transports: ['websocket', 'polling'],
      timeout: 5000,
      forceNew: true,
      ...socketOptionsRef.current,
    });

    socketRef.current = socket;

    // Register custom handlers BEFORE setting up connection listeners
    // This ensures we don't miss events that fire immediately on connect
    if (registerHandlersRef.current) {
      const cleanup = registerHandlersRef.current(socket);
      handlersCleanupRef.current = cleanup ?? null;
    }

    const handleConnect = () => {
      clearTimeoutRef();
      setStatus({ connected: true, loading: false, reconnecting: false, error: null });
      onConnectRef.current?.(socket);
    };

    const handleDisconnect = (reason: string) => {
      clearTimeoutRef();
      setStatus({ connected: false, loading: false, reconnecting: false, error: `Disconnected from server: ${reason}` });
      onDisconnectRef.current?.(reason, socket);
    };

    const handleConnectError = (error: Error) => {
      clearTimeoutRef();
      const message = onConnectErrorRef.current?.(error, socket) ?? error.message ?? 'Failed to connect to backend server.';
      setStatus({ connected: false, loading: false, reconnecting: false, error: message });
    };

    socket.on('connect', handleConnect);
    socket.on('disconnect', handleDisconnect);
    socket.on('connect_error', handleConnectError);

    if (connectionTimeoutMs > 0) {
      timeoutRef.current = window.setTimeout(() => {
        if (!socket.connected) {
          handleConnectError(new Error(timeoutMessage));
          socket.disconnect();
        }
      }, connectionTimeoutMs);
    }
  }, [
    teardownSocket,
    url,
    clearTimeoutRef,
    connectionTimeoutMs,
    timeoutMessage,
  ]);

  const disconnect = useCallback(() => {
    teardownSocket();
    setStatus({ ...defaultStatus });
  }, [teardownSocket]);

  const reconnect = useCallback(() => {
    connect();
  }, [connect]);

  const clearError = useCallback(() => {
    setStatus((prev) => ({ ...prev, error: null }));
  }, []);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      teardownSocket();
    };
  }, [autoConnect, connect, teardownSocket]);

  return {
    socket: socketRef.current,
    status,
    connect,
    reconnect,
    disconnect,
    clearError,
  };
}
