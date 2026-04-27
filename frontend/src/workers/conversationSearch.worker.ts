/// <reference lib="webworker" />

import {
  searchConversations,
  type ConversationSearchHit,
  type SearchableConversation,
} from '../utils/conversationSearch'

type SearchWorkerRequest = {
  requestId: number
  query: string
  conversations: SearchableConversation[]
}

type SearchWorkerResponse = {
  requestId: number
  hits: ConversationSearchHit[]
}

const workerScope: DedicatedWorkerGlobalScope = self as DedicatedWorkerGlobalScope

workerScope.onmessage = (event: MessageEvent<SearchWorkerRequest>) => {
  const { requestId, query, conversations } = event.data
  const hits = searchConversations(conversations, query)
  const response: SearchWorkerResponse = { requestId, hits }
  workerScope.postMessage(response)
}

export {}
