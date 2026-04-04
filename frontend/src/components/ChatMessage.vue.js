import { computed } from "vue";
import { cleanFileName, linkify } from "../utils/text";
const props = defineProps();
const __VLS_emit = defineEmits();
const activeTab = computed(() => props.activeCitationIndex ?? 0);
function getSectionLabel(citation) {
    if (!citation.section) {
        if (citation.page !== null && citation.page !== undefined) {
            return 'Page ' + citation.page;
        }
        return 'Source';
    }
    // If section is short enough (real section header), use it as-is
    if (citation.section.length <= 30) {
        return citation.section;
    }
    // For long sections, try to extract the first meaningful phrase
    // Split by common sentence delimiters and take the first part
    const firstPhrase = citation.section.split(/[,;.!?]/)[0].trim();
    if (firstPhrase.length > 30) {
        // If still too long, take first N characters and add ellipsis
        return firstPhrase.substring(0, 30) + '…';
    }
    return firstPhrase || 'Source';
}
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "message" },
    ...{ class: (__VLS_ctx.msg.role) },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
(__VLS_ctx.msg.role === 'user' ? 'You' : 'Assistant');
if (__VLS_ctx.msg.role === 'assistant' && !__VLS_ctx.msg.content && __VLS_ctx.asking) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "typing-dots" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ style: {} },
    });
    (__VLS_ctx.msg.content);
}
if (__VLS_ctx.msg.citations?.length) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "sources" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "source-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "citation-filename" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({
        ...{ style: {} },
    });
    (__VLS_ctx.cleanFileName(__VLS_ctx.msg.citations[__VLS_ctx.activeTab].fileName));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ style: {} },
    });
    for (const [citation, cIdx] of __VLS_getVForSourceType((__VLS_ctx.msg.citations))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.msg.citations?.length))
                        return;
                    __VLS_ctx.$emit('update:activeCitationIndex', cIdx);
                } },
            key: (cIdx),
            ...{ class: "citation-tab" },
            ...{ class: ({ active: __VLS_ctx.activeTab === cIdx }) },
        });
        (__VLS_ctx.getSectionLabel(citation));
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
        ...{ style: {} },
    });
    __VLS_asFunctionalDirective(__VLS_directives.vHtml)(null, { ...__VLS_directiveBindingRestFields, value: (__VLS_ctx.linkify(__VLS_ctx.msg.citations[__VLS_ctx.activeTab].text)) }, null, null);
}
/** @type {__VLS_StyleScopedClasses['message']} */ ;
/** @type {__VLS_StyleScopedClasses['typing-dots']} */ ;
/** @type {__VLS_StyleScopedClasses['sources']} */ ;
/** @type {__VLS_StyleScopedClasses['source-card']} */ ;
/** @type {__VLS_StyleScopedClasses['citation-filename']} */ ;
/** @type {__VLS_StyleScopedClasses['citation-tab']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            cleanFileName: cleanFileName,
            linkify: linkify,
            activeTab: activeTab,
            getSectionLabel: getSectionLabel,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
    __typeProps: {},
});
; /* PartiallyEnd: #4569/main.vue */
