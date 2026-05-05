import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the database module so the fire-and-forget IndexedDB writes in
// saveConversationToken() don't throw "database not initialized" in tests.
vi.mock('../../src/utils/database', () => ({
  ConversationTokensTable: {
    get: vi.fn(async () => null),
    set: vi.fn(async () => {}),
    getAllIds: vi.fn(async () => []),
    remove: vi.fn(async () => {}),
  },
}))

describe('Conversation Token Management', () => {
  // Module-level tokensCache in api.ts persists across tests, so we reset
  // modules in beforeEach to get a fresh Map for each test.
  let saveConversationToken: (id: string, token: string) => void
  let getConversationToken: (id: string) => string
  let getStoredConversationIds: () => string[]

  beforeEach(async () => {
    localStorage.clear();
    vi.resetModules();
    const api = await import('../../src/api');
    saveConversationToken = api.saveConversationToken;
    getConversationToken = api.getConversationToken;
    getStoredConversationIds = api.getStoredConversationIds;
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('should save and retrieve a conversation token', () => {
    const conversationId = 'conv-123';
    const token = 'token-abc-xyz';

    saveConversationToken(conversationId, token);
    const retrieved = getConversationToken(conversationId);

    expect(retrieved).toBe(token);
  });

  it('should return empty string for non-existent token', () => {
    const retrieved = getConversationToken('non-existent');
    expect(retrieved).toBe('');
  });

  it('should retrieve all stored conversation IDs', () => {
    saveConversationToken('conv-1', 'token-1');
    saveConversationToken('conv-2', 'token-2');
    saveConversationToken('conv-3', 'token-3');

    const ids = getStoredConversationIds();
    
    expect(ids).toHaveLength(3);
    expect(ids).toContain('conv-1');
    expect(ids).toContain('conv-2');
    expect(ids).toContain('conv-3');
  });

  it('should overwrite existing token', () => {
    saveConversationToken('conv-123', 'token-old');
    saveConversationToken('conv-123', 'token-new');

    const retrieved = getConversationToken('conv-123');
    expect(retrieved).toBe('token-new');
  });

  it('should return empty list when no tokens stored', () => {
    const ids = getStoredConversationIds();
    expect(ids).toEqual([]);
  });
});
