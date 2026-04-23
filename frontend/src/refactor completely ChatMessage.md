refactor completely ChatMessage.vue from scratch, step by step
- main requirement: accepts text, renders layout

- props: 
message: Message {
  id: string
  content: string
  role: 'user' | 'assistant' | 'system'
  timestamp: number
}
uploadedFiles: ['link_to_GCS.pdf', 'link2_to_GCS.doc']

watch for changes in message.content and re-render the component when it changes
- inside ChatMessage.vue, use TextFade.vue component, with :key="message.content" to ensure it re-renders when content changes
- TextFade.vue will handle the fade-in animation whenever the content changes (onMounted and onUpdated lifecycle hooks)
- TextFade.vue will not run animations on page load (only when new message / translation appears)
- TextFade.vue will be re-rendered with :key="message.content", which is standard Vue pattern
- TextFade.vue will be re-rendered with :key="message.content" when language change request has response with translatedo content

ChatMessage.vue handles internally:
- formatting message content in two columns - left : 1. "text + More..."" (as <MessageContent> sub-component) +  2,{right: big preview of prop.uploadedFiles files carousel - component <PreviewFiles :uploaded-files="props.uploadedFiles" />}  on desktop (wider screen)
- on smartphone (max width breakpoint rule), use current layout look (no big preview on right, uploaded files below as miniatures, but bigger - to full width, for screen like 768px)
- <PreviewPdf> component, <PreviewText>, <PreviewImg> etc
- translate in batch (single request - whole message), omit [action] (do not send it at all to Translate API, just extract text after [action:] and "reconstruct" [action] when receiving response)
- each [action] should be component <MessageContentAction> , and <MessageContentActionMore> grouping buttons
- "normal text action" is <Action> 

  first 3 "text prompts without action" from prompt response in welcome message + first 2 with [action] from prompt response in welcome message
  rest 5 with [action] from prompt response in welcome messag <= group using <MessageContentActionMore>

  similar rule for normal message (not welcome) of assistant

  first 2 "text prompts without action" from prompt response in welcome message + first 1 with [action] from prompt response in welcome message
  rest 5 with [action] from prompt response in welcome message <= group using subcomponent <MessageContentActionMore>

- cache translated message.content (do not repeat translation, store in LS - use translations on page restart from LS)
-  <ChangeLanguageButton> : changing language from like 'en' to 'pl' triggers translation, but "outside" <ChatMessage> - each <ChatMessage> will be re-rendered when translation is received from API
- "wrapper component" loads data from LS about translations after page load, and is receiving new incoming messages to re-render list of <ChatMessage>, but without unnecessary re-rendering of old message (they should have :key or something, to avoid unnecessary animations etc)
- also remember about displaying generating messages - initial text "Generating message" + animation to "rich text what is generated" is ok, but exceptionally for that scenario, keep same width of assistant message container during showing "rich text what is generated" (add prop true/false for message to control width - fixed or full)

FINALLY, rebuild whole component for displaying conversation by removing unnecessary layers of code, rethink whole solution again and keep it minimal ASAP