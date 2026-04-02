import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { 
  saveConversationToken, 
  getConversationToken, 
  getStoredConversationIds 
} from '../../src/api';

describe('Conversation Token Management', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
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

  it('should handle localStorage errors gracefully', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('invalid-json');
    const ids = getStoredConversationIds();
    expect(ids).toEqual([]);
  });
});
