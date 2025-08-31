// src/hooks/usePolling.ts
import { useState, useEffect, useCallback } from 'react';
import bffClient from '../api/bffClient';

export function usePolling<T>(url: string, intervalMs: number = 15000) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (isInitialLoad: boolean = false) => {
    if (isInitialLoad) {
      setIsLoading(true);
    }
    try {
      const response = await bffClient.get(url) as T;
      setData(response);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch data.');
    } finally {
      if (isInitialLoad) {
        setIsLoading(false);
      }
    }
  }, [url]);

  useEffect(() => {
    fetchData(true); // Initial fetch
    const intervalId = setInterval(() => fetchData(false), intervalMs);
    return () => clearInterval(intervalId);
  }, [fetchData, intervalMs]);

  // FIXED: Added 'refetch' to the return object
  return { data, isLoading, error, refetch: () => fetchData(true) };
}