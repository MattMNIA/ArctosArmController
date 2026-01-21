/**
 * Centralized API client for backend communication.
 *
 * This module provides a single point of configuration for all API calls,
 * eliminating hardcoded URLs throughout the codebase.
 */

// Use environment variable or default to localhost
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

/**
 * Custom error class for API errors with additional context.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly url: string;
  readonly data?: unknown;

  constructor(response: Response, data?: unknown) {
    const message = data && typeof data === 'object' && 'error' in data
      ? String((data as { error: unknown }).error)
      : `Request failed: ${response.status} ${response.statusText}`;

    super(message);
    this.name = 'ApiError';
    this.status = response.status;
    this.statusText = response.statusText;
    this.url = response.url;
    this.data = data;
  }
}

/**
 * Parse response as JSON, handling errors appropriately.
 */
async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: unknown;
    try {
      errorData = await response.json();
    } catch {
      // Response wasn't JSON, use status text
    }
    throw new ApiError(response, errorData);
  }
  return response.json();
}

/**
 * API client with methods for all HTTP verbs.
 */
export const api = {
  /**
   * Get the base URL for API calls.
   */
  getBaseUrl(): string {
    return API_BASE;
  },

  /**
   * Get the full URL for a path.
   */
  getUrl(path: string): string {
    return `${API_BASE}${path}`;
  },

  /**
   * Perform a GET request.
   */
  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`);
    return parseResponse<T>(response);
  },

  /**
   * Perform a POST request with optional JSON body.
   */
  async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    return parseResponse<T>(response);
  },

  /**
   * Perform a PUT request with JSON body.
   */
  async put<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return parseResponse<T>(response);
  },

  /**
   * Perform a DELETE request.
   */
  async delete<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
    });
    return parseResponse<T>(response);
  },
};

/**
 * Get the WebSocket URL for Socket.IO connections.
 */
export function getSocketUrl(): string {
  return API_BASE;
}

export default api;
