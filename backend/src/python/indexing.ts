import { config } from '../config.js'
import { runPythonScript } from './run-python.js'

export async function enrichMetadata(options: {
  filePaths: string[]
  exifMetadata?: Record<string, any>
  welcomeMessage?: string
}): Promise<Record<string, any>> {
  const response = await fetch(`${config.pythonServerUrl}/enrich-metadata`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_paths: options.filePaths,
      exif_metadata: options.exifMetadata || null,
      welcome_message: options.welcomeMessage || '',
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Enrich-metadata error (${response.status}): ${text}`)
  }

  return response.json()
}

export async function indexConversation(options: {
  conversationId: string
  collectionName: string
  files: string[]
  mode: 'script' | 'notebook'
}) {
  // Notebook mode still requires spawning a process (Jupyter/papermill)
  if (options.mode === 'notebook') {
    const args = [
      '--conversation-id',
      options.conversationId,
      '--collection-name',
      options.collectionName,
    ]
    for (const file of options.files) {
      args.push('--file', file)
    }
    return runPythonScript('run_notebook_indexer.py', args, {
      conversationId: options.conversationId,
      purpose: 'index',
    })
  }

  // Script mode: call persistent Python server
  const response = await fetch(`${config.pythonServerUrl}/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: options.conversationId,
      collection_name: options.collectionName,
      file_paths: options.files,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  const parsedJson = await response.json()
  return {
    stdout: JSON.stringify(parsedJson),
    stderr: '',
    parsedJson,
    stdoutLogPath: '',
    stderrLogPath: '',
  }
}

export async function describeUrl(options: {
  url: string
  conversationId: string
  collectionName: string
}) {
  const response = await fetch(`${config.pythonServerUrl}/describe-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: options.url,
      conversation_id: options.conversationId,
      collection_name: options.collectionName,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  const parsedJson = await response.json()
  return {
    stdout: JSON.stringify(parsedJson),
    stderr: '',
    parsedJson,
    stdoutLogPath: '',
    stderrLogPath: '',
  }
}
