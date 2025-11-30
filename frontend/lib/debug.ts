/**
 * Debug logging utility with environment-based controls
 * Only logs in development mode to prevent sensitive information exposure in production
 */

const isDevelopment = process.env.NODE_ENV === 'development';

export const debugLog = (...args: any[]) => {
  if (isDevelopment) {
    console.log('[DEBUG]', ...args);
  }
};

export const debugWarn = (...args: any[]) => {
  if (isDevelopment) {
    console.warn('[DEBUG]', ...args);
  }
};

export const debugError = (...args: any[]) => {
  if (isDevelopment) {
    console.error('[DEBUG]', ...args);
  }
};
