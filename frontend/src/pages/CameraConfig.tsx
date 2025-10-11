import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Camera,
  RefreshCw,
  ToggleLeft,
  SlidersHorizontal,
  Binary,
  CircuitBoard,
  GaugeCircle,
} from 'lucide-react';

interface ControlOption {
  value: number;
  label: string;
}

type ControlType = 'range' | 'toggle' | 'select';

interface RawCameraControl {
  id: string;
  label: string;
  type: ControlType;
  description?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: ControlOption[];
  value: number | boolean | null;
  default?: number | boolean;
}

interface CameraControl extends Omit<RawCameraControl, 'value'> {
  value: number | boolean;
}

interface CameraInfo {
  type: string;
  streamUrl?: string;
  controlBaseUrl?: string;
  preferredIndex?: number;
}

interface ControlsResponse {
  camera: CameraInfo;
  controls: RawCameraControl[];
}

type AdvancedBusyKey =
  | 'register-read'
  | 'register-write'
  | 'xclk'
  | 'pll'
  | 'window'
  | null;

type CameraStatusValue = number | boolean | string | null;
type CameraStatus = Record<string, CameraStatusValue>;

const REGISTER_DEFAULTS = {
  register: '0x00',
  mask: '0xFF',
  offset: '0',
  value: '0x00',
};

const PLL_DEFAULTS = {
  bypass: '0',
  mul: '4',
  sys: '1',
  root: '1',
  pre: '0',
  seld5: '1',
  pclken: '1',
  pclk: '1',
};

const WINDOW_DEFAULTS = {
  start_x: '0',
  start_y: '0',
  end_x: '640',
  end_y: '480',
  offset_x: '0',
  offset_y: '0',
  total_x: '640',
  total_y: '480',
  output_x: '640',
  output_y: '480',
  scaling: '0',
  binning: '0',
};

export default function CameraConfig() {
  const [controls, setControls] = useState<CameraControl[]>([]);
  const [cameraInfo, setCameraInfo] = useState<CameraInfo | null>(null);
  const [statusValues, setStatusValues] = useState<CameraStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [savingControl, setSavingControl] = useState<string | null>(null);
  const [advancedBusy, setAdvancedBusy] = useState<AdvancedBusyKey>(null);

  const [registerForm, setRegisterForm] = useState(REGISTER_DEFAULTS);
  const [registerReadResult, setRegisterReadResult] = useState<string | null>(null);
  const [xclkFrequency, setXclkFrequency] = useState('20');
  const [pllForm, setPllForm] = useState(PLL_DEFAULTS);
  const [windowForm, setWindowForm] = useState(WINDOW_DEFAULTS);

  const controlCount = useMemo(() => controls.length, [controls]);

  useEffect(() => {
    if (!success) {
      return undefined;
    }
    const timer = window.setTimeout(() => setSuccess(null), 3000);
    return () => window.clearTimeout(timer);
  }, [success]);

  const normalizeControl = useCallback((control: RawCameraControl): CameraControl => {
    if (control.type === 'toggle') {
      const rawValue = control.value ?? control.default ?? false;
      return { ...control, value: Boolean(rawValue) };
    }
    const fallback = Number(
      typeof control.default === 'number'
        ? control.default
        : control.min ?? 0
    );
    const numericValue =
      typeof control.value === 'number'
        ? control.value
        : typeof control.value === 'string'
        ? Number(control.value)
        : typeof control.default === 'number'
        ? control.default
        : fallback;

    return {
      ...control,
      value: Number.isFinite(numericValue) ? numericValue : fallback,
    };
  }, []);

  const fetchControls = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);

      const response = await fetch('/api/camera/controls');
      if (!response.ok) {
        throw new Error('Failed to load camera controls');
      }

      const data: ControlsResponse = await response.json();
      const normalizedControls = data.controls.map(normalizeControl);
      setControls(normalizedControls);
      setCameraInfo(data.camera);

      const statusResponse = await fetch('/api/camera/status');
      if (statusResponse.ok) {
        const statusData: CameraStatus = await statusResponse.json();
        setStatusValues(statusData);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load camera configuration');
    } finally {
      setLoading(false);
    }
  }, [normalizeControl]);

  useEffect(() => {
    fetchControls();
  }, [fetchControls]);

  const updateLocalControl = useCallback((controlId: string, value: number | boolean) => {
    setControls(prev =>
      prev.map(control =>
        control.id === controlId
          ? {
              ...control,
              value,
            }
          : control
      )
    );
  }, []);

  const submitControlUpdate = useCallback(
    async (control: CameraControl, newValue: number | boolean) => {
      setSavingControl(control.id);
      setError(null);
      setSuccess(null);

      try {
        const response = await fetch(`/api/camera/controls/${control.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ value: newValue }),
        });

        if (!response.ok) {
          throw new Error(`Failed to update ${control.label}`);
        }

        const payload = await response.json();
        const returnedValue = payload?.value ?? newValue;
        setControls(prev =>
          prev.map(existing =>
            existing.id === control.id
              ? {
                  ...existing,
                  value:
                    existing.type === 'toggle'
                      ? Boolean(returnedValue)
                      : Number(returnedValue),
                }
              : existing
          )
        );
        setSuccess(`${control.label} updated successfully`);
      } catch (err) {
        setError(err instanceof Error ? err.message : `Failed to update ${control.label}`);
        // Revert optimistic update
        setControls(prev => prev.map(existing => (existing.id === control.id ? control : existing)));
      } finally {
        setSavingControl(null);
      }
    },
    []
  );

  const handleToggle = (control: CameraControl) => {
    const nextValue = !Boolean(control.value);
    updateLocalControl(control.id, nextValue);
    submitControlUpdate(control, nextValue);
  };

  const handleRangeChange = (control: CameraControl, value: number) => {
    updateLocalControl(control.id, value);
  };

  const handleRangeCommit = (control: CameraControl, value: number) => {
    submitControlUpdate(control, value);
  };

  const handleSelectChange = (control: CameraControl, value: number) => {
    updateLocalControl(control.id, value);
    submitControlUpdate(control, value);
  };

  const handleRegisterFormChange = (field: keyof typeof REGISTER_DEFAULTS, value: string) => {
    setRegisterForm(prev => ({ ...prev, [field]: value }));
  };

  const handleRegisterRead = async () => {
    setAdvancedBusy('register-read');
    setRegisterReadResult(null);
    setError(null);
    try {
      const response = await fetch('/api/camera/registers/read', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          register: registerForm.register,
          mask: registerForm.mask,
          offset: registerForm.offset,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to read register');
      }

      const data = await response.json();
      const numericValue = typeof data.value === 'number' ? data.value : NaN;
      const formattedValue = data.hex
        ? data.hex
        : Number.isFinite(numericValue)
        ? `0x${numericValue.toString(16)}`
        : String(data.value ?? '');
      setRegisterReadResult(formattedValue);
      setSuccess(`Register ${registerForm.register} read successfully`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read register');
    } finally {
      setAdvancedBusy(null);
    }
  };

  const handleRegisterWrite = async () => {
    setAdvancedBusy('register-write');
    setError(null);
    try {
      const response = await fetch('/api/camera/registers/write', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(registerForm),
      });

      if (!response.ok) {
        throw new Error('Failed to write register');
      }

      await response.json();
      setSuccess(`Register ${registerForm.register} updated`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to write register');
    } finally {
      setAdvancedBusy(null);
    }
  };

  const handleXclkUpdate = async () => {
    setAdvancedBusy('xclk');
    setError(null);
    try {
      const response = await fetch('/api/camera/xclk', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ frequency: xclkFrequency }),
      });

      if (!response.ok) {
        throw new Error('Failed to update XCLK frequency');
      }

      await response.json();
      setSuccess('XCLK frequency updated');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update XCLK frequency');
    } finally {
      setAdvancedBusy(null);
    }
  };

  const handlePllUpdate = async () => {
    setAdvancedBusy('pll');
    setError(null);
    try {
      const response = await fetch('/api/camera/pll', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(pllForm),
      });

      if (!response.ok) {
        throw new Error('Failed to configure PLL');
      }

      await response.json();
      setSuccess('PLL configuration applied');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to configure PLL');
    } finally {
      setAdvancedBusy(null);
    }
  };

  const handleWindowUpdate = async () => {
    setAdvancedBusy('window');
    setError(null);
    try {
      const response = await fetch('/api/camera/window', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(windowForm),
      });

      if (!response.ok) {
        throw new Error('Failed to configure window');
      }

      await response.json();
      setSuccess('Sensor window updated');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to configure window');
    } finally {
      setAdvancedBusy(null);
    }
  };

  const renderControl = (control: CameraControl) => {
    const busy = savingControl === control.id;
    const description = control.description;

    if (control.type === 'toggle') {
      const enabled = Boolean(control.value);
      return (
        <motion.button
          key={control.id}
          onClick={() => handleToggle(control)}
          whileTap={{ scale: 0.95 }}
          className={`flex items-center justify-between w-full px-4 py-3 rounded-lg border transition-colors duration-200 ${
            enabled
              ? 'bg-blue-900/30 border-blue-500/40 text-blue-100'
              : 'bg-gray-800/50 border-gray-700 text-gray-200 hover:border-blue-500/40'
          }`}
        >
          <div className="flex flex-col gap-1 text-left">
            <span className="font-semibold">{control.label}</span>
            {description && <span className="text-sm text-gray-400">{description}</span>}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{enabled ? 'On' : 'Off'}</span>
            <ToggleLeft
              className={`w-6 h-6 transition-colors ${enabled ? 'text-blue-400 rotate-180' : 'text-gray-500'}`}
            />
          </div>
        </motion.button>
      );
    }

    if (control.type === 'select') {
      return (
        <div
          key={control.id}
          className="bg-gray-800/50 border border-gray-700/60 rounded-xl p-4 space-y-3"
        >
          <div>
            <p className="font-semibold text-white">{control.label}</p>
            {description && <p className="text-sm text-gray-400 mt-1">{description}</p>}
          </div>
          <select
            value={String(control.value)}
            onChange={(event) => handleSelectChange(control, Number(event.target.value))}
            className="w-full bg-gray-900/60 border border-gray-700 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          >
            {control.options?.map(option => (
              <option key={`${control.id}-${option.value}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {busy && <p className="text-xs text-blue-400">Updating…</p>}
        </div>
      );
    }

    const min = control.min ?? 0;
    const max = control.max ?? 100;
    const step = control.step ?? 1;
    const numericValue = Number(control.value);

    return (
      <div
        key={control.id}
        className="bg-gray-800/50 border border-gray-700/60 rounded-xl p-4 space-y-4"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-semibold text-white">{control.label}</p>
            {description && <p className="text-sm text-gray-400 mt-1">{description}</p>}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={Number.isFinite(numericValue) ? numericValue : ''}
              min={min}
              max={max}
              step={step}
              onChange={(event) => {
                const value = Number(event.target.value);
                if (Number.isFinite(value)) {
                  handleRangeChange(control, value);
                }
              }}
              onBlur={(event) => {
                const value = Number(event.target.value);
                if (Number.isFinite(value)) {
                  handleRangeCommit(control, value);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  const value = Number((event.target as HTMLInputElement).value);
                  if (Number.isFinite(value)) {
                    handleRangeCommit(control, value);
                  }
                }
              }}
              className="w-24 bg-gray-900/60 border border-gray-700 rounded-lg px-3 py-1.5 text-right text-white focus:border-blue-500 focus:outline-none"
            />
            <span className="text-sm text-gray-400">[{min} – {max}]</span>
          </div>
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={Number.isFinite(numericValue) ? numericValue : min}
          onChange={(event) => handleRangeChange(control, Number(event.target.value))}
          onMouseUp={(event) => handleRangeCommit(control, Number((event.target as HTMLInputElement).value))}
          onTouchEnd={(event) =>
            handleRangeCommit(control, Number((event.target as HTMLInputElement).value))
          }
          className="w-full accent-blue-500"
        />
        {busy && <p className="text-xs text-blue-400 text-right">Updating…</p>}
      </div>
    );
  };

  const isRegisterBusy = advancedBusy === 'register-read' || advancedBusy === 'register-write';

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-7xl mx-auto p-6"
    >
      <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
            <Camera className="w-8 h-8 text-blue-400" />
            Camera Configuration
          </h1>
          <p className="text-gray-400">
            Adjust ESP32 camera settings, register values, and sensor timing from a single dashboard.
          </p>
          {cameraInfo && (
            <p className="text-sm text-gray-500 mt-2">
              Active camera: <span className="text-gray-300 font-medium">{cameraInfo.type?.toUpperCase() ?? 'Unknown'}</span>
              {cameraInfo.streamUrl && (
                <span className="ml-2">
                  • Stream URL: <span className="text-gray-300">{cameraInfo.streamUrl}</span>
                </span>
              )}
              {cameraInfo.controlBaseUrl && (
                <span className="ml-2">
                  • Control API: <span className="text-gray-300">{cameraInfo.controlBaseUrl}</span>
                </span>
              )}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <motion.button
            onClick={fetchControls}
            whileTap={{ scale: 0.95 }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800/70 border border-gray-700 text-gray-200 hover:text-white hover:border-blue-500/60 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </motion.button>
          <span className="text-sm text-gray-500">{controlCount} controls</span>
        </div>
      </header>

      {error && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-4 bg-red-900/20 border border-red-500/40 rounded-lg text-red-200"
        >
          {error}
        </motion.div>
      )}

      {success && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-4 bg-green-900/20 border border-green-500/40 rounded-lg text-green-200"
        >
          {success}
        </motion.div>
      )}

      {statusValues && (
        <section className="mb-8 bg-gray-900/40 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3 text-gray-300">
            <GaugeCircle className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold">Current Sensor Status</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm text-gray-300">
            {Object.entries(statusValues).map(([key, value]) => {
              const displayValue =
                typeof value === 'boolean'
                  ? value
                    ? 'On'
                    : 'Off'
                  : value ?? '—';
              return (
                <div key={key} className="bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2">
                  <p className="font-semibold text-gray-200">{key}</p>
                  <p className="text-gray-400">{displayValue}</p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="mb-10">
        <div className="flex items-center gap-2 text-gray-300 mb-4">
          <SlidersHorizontal className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg font-semibold">Image Controls</h2>
        </div>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {controls.map(renderControl)}
        </div>
      </section>

      {cameraInfo?.type === 'ip' && (
        <section className="space-y-10">
          <div className="flex items-center gap-2 text-gray-300">
            <Binary className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold">Register Access</h2>
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-5 space-y-4">
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <label className="flex flex-col text-sm text-gray-300">
                    Register
                    <input
                      value={registerForm.register}
                      onChange={(event) => handleRegisterFormChange('register', event.target.value)}
                      className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col text-sm text-gray-300">
                    Mask
                    <input
                      value={registerForm.mask}
                      onChange={(event) => handleRegisterFormChange('mask', event.target.value)}
                      className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col text-sm text-gray-300">
                    Offset
                    <input
                      value={registerForm.offset}
                      onChange={(event) => handleRegisterFormChange('offset', event.target.value)}
                      className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col text-sm text-gray-300">
                    Value
                    <input
                      value={registerForm.value}
                      onChange={(event) => handleRegisterFormChange('value', event.target.value)}
                      className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <motion.button
                    whileTap={{ scale: 0.95 }}
                    onClick={handleRegisterRead}
                    className={`px-4 py-2 rounded-lg border transition-colors ${
                      isRegisterBusy
                        ? 'bg-gray-900/60 border-gray-800 text-gray-500 cursor-not-allowed'
                        : 'bg-gray-800/70 border-gray-700 text-gray-200 hover:border-blue-500/60 hover:text-white'
                    }`}
                    disabled={isRegisterBusy}
                  >
                    Read Register
                  </motion.button>
                  <motion.button
                    whileTap={{ scale: 0.95 }}
                    onClick={handleRegisterWrite}
                    className={`px-4 py-2 rounded-lg border text-white transition-colors ${
                      isRegisterBusy
                        ? 'bg-blue-900/40 border-blue-800 cursor-not-allowed'
                        : 'bg-blue-600/70 border-blue-500 hover:bg-blue-600'
                    }`}
                    disabled={isRegisterBusy}
                  >
                    Write Register
                  </motion.button>
                  {isRegisterBusy && (
                    <span className="text-xs text-blue-400">Processing…</span>
                  )}
                </div>
                {registerReadResult && (
                  <div className="bg-gray-800/60 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                    Value: {registerReadResult}
                  </div>
                )}
              </div>
            </div>

            <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-5 space-y-5">
              <div className="flex items-center gap-2 text-gray-300">
                <CircuitBoard className="w-5 h-5 text-blue-400" />
                <h3 className="text-base font-semibold">Clock Configuration</h3>
              </div>
              <label className="flex flex-col text-sm text-gray-300">
                XCLK Frequency (MHz)
                <input
                  value={xclkFrequency}
                  onChange={(event) => setXclkFrequency(event.target.value)}
                  className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <motion.button
                whileTap={{ scale: 0.95 }}
                onClick={handleXclkUpdate}
                disabled={advancedBusy === 'xclk'}
                className={`px-4 py-2 rounded-lg border text-white transition-colors ${
                  advancedBusy === 'xclk'
                    ? 'bg-blue-900/40 border-blue-800 cursor-not-allowed'
                    : 'bg-blue-600/70 border-blue-500 hover:bg-blue-600'
                }`}
              >
                Apply XCLK
              </motion.button>

              <div className="grid grid-cols-2 gap-3">
                {Object.entries(pllForm).map(([field, value]) => (
                  <label key={field} className="flex flex-col text-sm text-gray-300">
                    {field.toUpperCase()}
                    <input
                      value={value}
                      onChange={(event) => setPllForm(prev => ({ ...prev, [field]: event.target.value }))}
                      className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </label>
                ))}
              </div>
              <motion.button
                whileTap={{ scale: 0.95 }}
                onClick={handlePllUpdate}
                disabled={advancedBusy === 'pll'}
                className={`px-4 py-2 rounded-lg border text-white transition-colors ${
                  advancedBusy === 'pll'
                    ? 'bg-blue-900/40 border-blue-800 cursor-not-allowed'
                    : 'bg-blue-600/70 border-blue-500 hover:bg-blue-600'
                }`}
              >
                Apply PLL Settings
              </motion.button>
            </div>
          </div>

          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-5 space-y-5">
            <div className="flex items-center gap-2 text-gray-300">
              <Camera className="w-5 h-5 text-blue-400" />
              <h3 className="text-base font-semibold">Sensor Window</h3>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(windowForm).map(([field, value]) => (
                <label key={field} className="flex flex-col text-sm text-gray-300">
                  {field.replace('_', ' ').toUpperCase()}
                  <input
                    value={value}
                    onChange={(event) => setWindowForm(prev => ({ ...prev, [field]: event.target.value }))}
                    className="mt-1 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700 text-white focus:border-blue-500 focus:outline-none"
                  />
                </label>
              ))}
            </div>
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={handleWindowUpdate}
              disabled={advancedBusy === 'window'}
              className={`px-4 py-2 rounded-lg border text-white transition-colors ${
                advancedBusy === 'window'
                  ? 'bg-blue-900/40 border-blue-800 cursor-not-allowed'
                  : 'bg-blue-600/70 border-blue-500 hover:bg-blue-600'
              }`}
            >
              Apply Window Configuration
            </motion.button>
          </div>
        </section>
      )}
    </motion.div>
  );
}
