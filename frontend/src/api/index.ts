/**
 * API module exports.
 *
 * Usage:
 *   import { api, getSocketUrl, ApiError } from '../api';
 *
 *   // GET request
 *   const data = await api.get('/api/teleop/modes');
 *
 *   // POST request
 *   await api.post('/api/teleop/start', { mode: 'keyboard' });
 *
 *   // Socket connection
 *   const socket = io(getSocketUrl());
 */

export { api, ApiError, getSocketUrl } from './client';
