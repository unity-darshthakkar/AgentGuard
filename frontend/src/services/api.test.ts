import { describe, expect, it } from 'vitest';

describe('development API routing', () => {
  it('uses the same-origin /api proxy in development', async () => {
    const source = await import('./api');
    expect(source.default.defaults.baseURL).toBe('/api');
  });
});
