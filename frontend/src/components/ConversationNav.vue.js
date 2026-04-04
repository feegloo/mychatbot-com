import { ref, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { listMyConversations } from "../api";
import { cleanFileName } from "../utils/text";
const __VLS_emit = defineEmits();
function convLabel(conv) {
    if (conv.displayName)
        return conv.displayName;
    if (conv.fileNames?.length) {
        return conv.fileNames.map(cleanFileName).join(", ");
    }
    return `Conversation ${conv.conversationId.slice(0, 8)}…`;
}
const route = useRoute();
const conversations = ref([]);
const loading = ref(false);
const currentId = ref("");
let pollHandle;
function hasProcessing() {
    return conversations.value.some(c => c.status === "processing");
}
function startPolling() {
    stopPolling();
    pollHandle = window.setInterval(async () => {
        await load();
        if (!hasProcessing())
            stopPolling();
    }, 1500);
}
function stopPolling() {
    if (pollHandle !== undefined) {
        clearInterval(pollHandle);
        pollHandle = undefined;
    }
}
async function load() {
    loading.value = true;
    try {
        conversations.value = await listMyConversations();
        if (hasProcessing() && pollHandle === undefined) {
            startPolling();
        }
    }
    catch {
        // silently fail – sidebar is non-critical
    }
    finally {
        loading.value = false;
    }
}
watch(() => route.params.conversationId, (id) => {
    currentId.value = id || "";
}, { immediate: true });
// Reload list when navigating to a new conversation (e.g. after upload)
watch(() => route.path, () => load());
onMounted(() => {
    load();
    window.addEventListener('conversation-updated', load);
});
onUnmounted(() => {
    stopPolling();
    window.removeEventListener('conversation-updated', load);
});
onMounted(load);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
    ...{ class: "conv-nav" },
});
const __VLS_0 = {}.RouterLink;
/** @type {[typeof __VLS_components.RouterLink, typeof __VLS_components.routerLink, typeof __VLS_components.RouterLink, typeof __VLS_components.routerLink, ]} */ ;
// @ts-ignore
const __VLS_1 = __VLS_asFunctionalComponent(__VLS_0, new __VLS_0({
    ...{ 'onClick': {} },
    to: "/",
    ...{ class: "conv-nav-new button" },
}));
const __VLS_2 = __VLS_1({
    ...{ 'onClick': {} },
    to: "/",
    ...{ class: "conv-nav-new button" },
}, ...__VLS_functionalComponentArgsRest(__VLS_1));
let __VLS_4;
let __VLS_5;
let __VLS_6;
const __VLS_7 = {
    onClick: (...[$event]) => {
        __VLS_ctx.$emit('navigate');
    }
};
__VLS_3.slots.default;
var __VLS_3;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "conv-nav-list" },
});
for (const [conv] of __VLS_getVForSourceType((__VLS_ctx.conversations))) {
    const __VLS_8 = {}.RouterLink;
    /** @type {[typeof __VLS_components.RouterLink, typeof __VLS_components.routerLink, typeof __VLS_components.RouterLink, typeof __VLS_components.routerLink, ]} */ ;
    // @ts-ignore
    const __VLS_9 = __VLS_asFunctionalComponent(__VLS_8, new __VLS_8({
        ...{ 'onClick': {} },
        key: (conv.conversationId),
        to: (`/c/${conv.conversationId}`),
        ...{ class: "conv-nav-item" },
        ...{ class: ({ active: conv.conversationId === __VLS_ctx.currentId }) },
    }));
    const __VLS_10 = __VLS_9({
        ...{ 'onClick': {} },
        key: (conv.conversationId),
        to: (`/c/${conv.conversationId}`),
        ...{ class: "conv-nav-item" },
        ...{ class: ({ active: conv.conversationId === __VLS_ctx.currentId }) },
    }, ...__VLS_functionalComponentArgsRest(__VLS_9));
    let __VLS_12;
    let __VLS_13;
    let __VLS_14;
    const __VLS_15 = {
        onClick: (...[$event]) => {
            __VLS_ctx.$emit('navigate');
        }
    };
    __VLS_11.slots.default;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "conv-nav-name" },
    });
    (__VLS_ctx.convLabel(conv));
    if (conv.status === 'processing') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "conv-nav-dot processing" },
        });
    }
    else if (conv.status === 'failed') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "conv-nav-dot failed" },
        });
    }
    var __VLS_11;
}
if (!__VLS_ctx.conversations.length && !__VLS_ctx.loading) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "conv-nav-empty" },
    });
}
/** @type {__VLS_StyleScopedClasses['conv-nav']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-new']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-list']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-item']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-name']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-dot']} */ ;
/** @type {__VLS_StyleScopedClasses['processing']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-dot']} */ ;
/** @type {__VLS_StyleScopedClasses['failed']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-nav-empty']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            convLabel: convLabel,
            conversations: conversations,
            loading: loading,
            currentId: currentId,
        };
    },
    __typeEmits: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
});
; /* PartiallyEnd: #4569/main.vue */
