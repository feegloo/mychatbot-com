import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { config } from '../src/config';

describe('Config', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('should have required values', () => {
    expect(config.port).toBeGreaterThan(0);
    expect(config.databaseUrl).toBeDefined();
    expect(config.chromaMode).toBeDefined();
  });

  it('should have valid storage provider', () => {
    expect(['disk', 'cloud']).toContain(config.storageProvider);
  });

  it('should resolve paths correctly', () => {
    expect(config.storageRoot).toBeDefined();
    expect(config.pythonProjectRoot).toBeDefined();
  });

  it('should have valid Chroma configuration', () => {
    if (config.chromaMode === 'cloud') {
      expect(config.chromaApiKey).toBeDefined();
      expect(config.chromaTenant).toBeDefined();
    }
  });
});
