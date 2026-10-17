import { useEffect, useState } from 'react';

export type ServerStatus = 'checking' | 'online' | 'offline';

/**
 * Pings the FastAPI liveness route once on mount.
 * The home screen shows the result so a broken demo setup is obvious before anyone sings.
 */
export function useServerStatus(): ServerStatus {
  const [status, setStatus] = useState<ServerStatus>('checking');

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal })
      .then((res) => setStatus(res.ok ? 'online' : 'offline'))
      .catch((err: unknown) => {
        if ((err as Error).name !== 'AbortError') setStatus('offline');
      });
    return () => controller.abort();
  }, []);

  return status;
}
