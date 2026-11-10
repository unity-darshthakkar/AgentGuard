import { afterEach, describe, expect, it, vi } from 'vitest';
import { AxiosError } from 'axios';

describe('development API routing', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses the same-origin /api proxy in development', async () => {
    const source = await import('./api');
    expect(source.default.defaults.baseURL).toBe('/api');
  });

  it('returns immediately when a safe GET responds', async () => {
    const { readOnlyGet } = await import('./api');
    const request = vi.fn().mockResolvedValue('ready');
    await expect(readOnlyGet(request)).resolves.toBe('ready');
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('shares readiness polling and recovers after a timeout', async () => {
    const { api, readOnlyGet } = await import('./api');
    vi.spyOn(api, 'get').mockResolvedValue({ data: { status: 'healthy' } } as any);
    const timeout = new AxiosError('timeout', 'ECONNABORTED');
    const first = vi.fn().mockRejectedValueOnce(timeout).mockResolvedValue('first-ready');
    const second = vi.fn().mockRejectedValueOnce(timeout).mockResolvedValue('second-ready');
    await expect(Promise.all([readOnlyGet(first), readOnlyGet(second)])).resolves.toEqual(['first-ready', 'second-ready']);
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(first).toHaveBeenCalledTimes(2);
    expect(second).toHaveBeenCalledTimes(2);
  });

  it('does not retry genuine authorization errors', async () => {
    const { readOnlyGet } = await import('./api');
    const error = new AxiosError('forbidden', 'ERR_BAD_REQUEST', undefined, undefined, { status: 403 } as any);
    const request = vi.fn().mockRejectedValue(error);
    await expect(readOnlyGet(request)).rejects.toBe(error);
    expect(request).toHaveBeenCalledTimes(1);
  });
});
