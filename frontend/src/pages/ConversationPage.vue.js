import { computed, onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import { askQuestion, getConversation, } from "../api";
import { cleanFileName } from "../utils/text";
import ConversationHeader from "../components/ConversationHeader.vue";
import ChatMessageItem from "../components/ChatMessage.vue";
import ConversationSidebar from "../components/ConversationSidebar.vue";
const props = defineProps();
const conversationId = props.conversationId;
const question = ref("");
const asking = ref(false);
const questionInput = ref(null);
const chatContainer = ref(null);
const sidebarRef = ref(null);
const loaded = ref(false);
const status = ref({
    conversationId,
    displayName: null,
    status: "processing",
    role: "viewer",
    files: [],
    messages: [],
    suggestedQuestions: [],
    accessRequests: []
});
const messages = ref([]);
const activeCitationTab = ref({});
const canUpload = computed(() => status.value.role === "owner" || status.value.role === "editor");
const conversationTitle = computed(() => {
    if (status.value.displayName)
        return status.value.displayName;
    if (status.value.files.length) {
        return status.value.files.map(f => cleanFileName(f.originalName)).join(", ");
    }
    return `Conversation ${conversationId.slice(0, 8)}…`;
});
watch(conversationTitle, (title) => {
    document.title = `chatrag.app | ${title}`;
}, { immediate: true });
async function loadConversation() {
    const response = await getConversation(conversationId);
    status.value = response;
    if (!asking.value) {
        messages.value = response.messages || [];
    }
    loaded.value = true;
}
async function onReload() {
    await loadConversation();
    window.dispatchEvent(new CustomEvent('conversation-updated'));
}
function scrollToBottom() {
    if (chatContainer.value) {
        const scrollHeight = chatContainer.value.scrollHeight;
        chatContainer.value.scrollTop = scrollHeight;
    }
}
async function ask() {
    if (!question.value.trim())
        return;
    if (status.value.status !== "ready") {
        await loadConversation();
        return;
    }
    asking.value = true;
    const currentQuestion = question.value;
    question.value = "";
    messages.value.push({ role: "user", content: currentQuestion });
    const assistantPlaceholder = { role: "assistant", content: "" };
    messages.value.push(assistantPlaceholder);
    try {
        const response = await askQuestion(conversationId, currentQuestion);
        assistantPlaceholder.content = response.answer;
        assistantPlaceholder.citations = response.citations;
        await loadConversation();
    }
    finally {
        asking.value = false;
    }
}
function submitQuestion() {
    if (asking.value || !question.value.trim())
        return;
    ask();
    if (questionInput.value) {
        questionInput.value.style.height = 'auto';
    }
}
function autoResize(e) {
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
}
let prevMessageCount = 0;
watch(() => messages.value.length, async (newLen) => {
    if (newLen > prevMessageCount) {
        await nextTick();
        setTimeout(() => scrollToBottom(), 0);
    }
    prevMessageCount = newLen;
});
let intervalHandle;
onMounted(async () => {
    await loadConversation();
    loaded.value = true;
    await nextTick();
    setTimeout(() => scrollToBottom(), 100);
    intervalHandle = window.setInterval(async () => {
        await loadConversation();
        sidebarRef.value?.pollAccessRequest();
    }, 1000);
});
onUnmounted(() => {
    if (intervalHandle !== undefined) {
        clearInterval(intervalHandle);
    }
});
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "page" },
});
/** @type {[typeof ConversationHeader, ]} */ ;
// @ts-ignore
const __VLS_0 = __VLS_asFunctionalComponent(ConversationHeader, new ConversationHeader({
    ...{ 'onRenamed': {} },
    status: (__VLS_ctx.status),
    conversationId: (__VLS_ctx.conversationId),
    conversationTitle: (__VLS_ctx.conversationTitle),
    canUpload: (__VLS_ctx.canUpload),
}));
const __VLS_1 = __VLS_0({
    ...{ 'onRenamed': {} },
    status: (__VLS_ctx.status),
    conversationId: (__VLS_ctx.conversationId),
    conversationTitle: (__VLS_ctx.conversationTitle),
    canUpload: (__VLS_ctx.canUpload),
}, ...__VLS_functionalComponentArgsRest(__VLS_0));
let __VLS_3;
let __VLS_4;
let __VLS_5;
const __VLS_6 = {
    onRenamed: (...[$event]) => {
        __VLS_ctx.status.displayName = $event;
    }
};
var __VLS_2;
if (__VLS_ctx.status.errorMessage) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ style: {} },
    });
    (__VLS_ctx.status.errorMessage);
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "grid grid-2" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
    ...{ class: "chat-panel" },
});
if (__VLS_ctx.loaded && __VLS_ctx.status.status !== 'ready') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ style: {} },
    });
    (__VLS_ctx.status.status);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.br)({});
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "chat-log" },
    ref: "chatContainer",
    ...{ style: {} },
});
/** @type {typeof __VLS_ctx.chatContainer} */ ;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
for (const [msg, index] of __VLS_getVForSourceType((__VLS_ctx.messages))) {
    /** @type {[typeof ChatMessageItem, ]} */ ;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent(ChatMessageItem, new ChatMessageItem({
        ...{ 'onUpdate:activeCitationIndex': {} },
        key: (msg.id || index),
        msg: (msg),
        asking: (__VLS_ctx.asking),
        activeCitationIndex: (__VLS_ctx.activeCitationTab[index] ?? 0),
    }));
    const __VLS_8 = __VLS_7({
        ...{ 'onUpdate:activeCitationIndex': {} },
        key: (msg.id || index),
        msg: (msg),
        asking: (__VLS_ctx.asking),
        activeCitationIndex: (__VLS_ctx.activeCitationTab[index] ?? 0),
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    let __VLS_10;
    let __VLS_11;
    let __VLS_12;
    const __VLS_13 = {
        'onUpdate:activeCitationIndex': (...[$event]) => {
            __VLS_ctx.activeCitationTab[index] = $event;
        }
    };
    var __VLS_9;
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "chat-input-bar" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
    ...{ onInput: (__VLS_ctx.autoResize) },
    ...{ onKeydown: (__VLS_ctx.submitQuestion) },
    ref: "questionInput",
    ...{ class: "chat-textarea" },
    value: (__VLS_ctx.question),
    placeholder: "Ask a question...",
    rows: "1",
});
/** @type {typeof __VLS_ctx.questionInput} */ ;
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.submitQuestion) },
    ...{ class: "send-btn" },
    disabled: (__VLS_ctx.asking || !__VLS_ctx.question.trim()),
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
    width: "18",
    height: "18",
    viewBox: "0 0 24 24",
    fill: "currentColor",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
    d: "M2.01 21L23 12 2.01 3 2 10l15 2-15 2z",
});
/** @type {[typeof ConversationSidebar, ]} */ ;
// @ts-ignore
const __VLS_14 = __VLS_asFunctionalComponent(ConversationSidebar, new ConversationSidebar({
    ...{ 'onReload': {} },
    ...{ 'onSelectQuestion': {} },
    ref: "sidebarRef",
    status: (__VLS_ctx.status),
    conversationId: (__VLS_ctx.conversationId),
    canUpload: (__VLS_ctx.canUpload),
}));
const __VLS_15 = __VLS_14({
    ...{ 'onReload': {} },
    ...{ 'onSelectQuestion': {} },
    ref: "sidebarRef",
    status: (__VLS_ctx.status),
    conversationId: (__VLS_ctx.conversationId),
    canUpload: (__VLS_ctx.canUpload),
}, ...__VLS_functionalComponentArgsRest(__VLS_14));
let __VLS_17;
let __VLS_18;
let __VLS_19;
const __VLS_20 = {
    onReload: (__VLS_ctx.onReload)
};
const __VLS_21 = {
    onSelectQuestion: (...[$event]) => {
        __VLS_ctx.question = $event;
        __VLS_ctx.submitQuestion();
    }
};
/** @type {typeof __VLS_ctx.sidebarRef} */ ;
var __VLS_22 = {};
var __VLS_16;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['grid']} */ ;
/** @type {__VLS_StyleScopedClasses['grid-2']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-log']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-input-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-textarea']} */ ;
/** @type {__VLS_StyleScopedClasses['send-btn']} */ ;
// @ts-ignore
var __VLS_23 = __VLS_22;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            ConversationHeader: ConversationHeader,
            ChatMessageItem: ChatMessageItem,
            ConversationSidebar: ConversationSidebar,
            conversationId: conversationId,
            question: question,
            asking: asking,
            questionInput: questionInput,
            chatContainer: chatContainer,
            sidebarRef: sidebarRef,
            loaded: loaded,
            status: status,
            messages: messages,
            activeCitationTab: activeCitationTab,
            canUpload: canUpload,
            conversationTitle: conversationTitle,
            onReload: onReload,
            submitQuestion: submitQuestion,
            autoResize: autoResize,
        };
    },
    __typeProps: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeProps: {},
});
; /* PartiallyEnd: #4569/main.vue */
