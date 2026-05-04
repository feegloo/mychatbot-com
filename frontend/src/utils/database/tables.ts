export enum Tables {
  CONFIGURATIONS = 'configurations',
  TRANSLATIONS = 'translations',
  CONVERSATION_TOKENS = 'conversationTokens',
  CONVERSATION_LANGUAGES = 'conversationLanguages',
  CHECKLIST_STATES = 'checklistStates',
}

/**
 * Dexie stores — primary key definition and indexes per table.
 *
 * configurations:      key-value bag for scalar settings (homePageLang, sidebarCollapsed, etc.)
 * translations:        per-message translation cache, keyed by [lang+messageId]
 * conversationTokens:  viewer access tokens, keyed by conversationId
 * conversationLanguages: user-chosen display language per conversation
 * checklistStates:     checked-box indices for message checklists
 */
export const stores: Record<Tables, string> = {
  configurations: 'key',
  translations: '[lang+messageId]',
  conversationTokens: 'conversationId',
  conversationLanguages: 'conversationId',
  checklistStates: 'messageId',
}
