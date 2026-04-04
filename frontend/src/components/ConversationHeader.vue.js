import { ref, nextTick } from "vue";
import { renameConversation } from "../api";
const props = defineProps();
const emit = defineEmits();
const editingName = ref(false);
const editNameValue = ref("");
const nameInput = ref(null);
const copied = ref(false);
async function startRename() {
    editingName.value = true;
    editNameValue.value = props.status.displayName || props.conversationTitle;
    await nextTick();
    nameInput.value?.select();
}
async function saveRename() {
    if (!editingName.value)
        return;
    editingName.value = false;
    const trimmed = editNameValue.value.trim();
    if (!trimmed || trimmed === props.status.displayName)
        return;
    await renameConversation(props.conversationId, trimmed);
    emit("renamed", trimmed);
}
async function copyUrl() {
    await navigator.clipboard.writeText(window.location.href);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
}
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "header" },
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
if (!__VLS_ctx.editingName) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({
        ...{ onClick: (...[$event]) => {
                if (!(!__VLS_ctx.editingName))
                    return;
                __VLS_ctx.canUpload && __VLS_ctx.startRename();
            } },
        ...{ class: "conv-title" },
        title: (__VLS_ctx.canUpload ? 'Click to rename' : ''),
        ...{ style: (__VLS_ctx.canUpload ? 'cursor: pointer' : '') },
    });
    (__VLS_ctx.conversationTitle);
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onKeydown: (__VLS_ctx.saveRename) },
        ...{ onKeydown: (...[$event]) => {
                if (!!(!__VLS_ctx.editingName))
                    return;
                __VLS_ctx.editingName = false;
            } },
        ...{ onBlur: (__VLS_ctx.saveRename) },
        ref: "nameInput",
        ...{ class: "conv-title-input" },
    });
    (__VLS_ctx.editNameValue);
    /** @type {typeof __VLS_ctx.nameInput} */ ;
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "header-badges" },
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "status-badge" },
});
(__VLS_ctx.status.status);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "status-badge" },
});
(__VLS_ctx.status.role);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "header-actions" },
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.copyUrl) },
    ...{ class: "button secondary" },
    ...{ style: {} },
});
if (__VLS_ctx.copied) {
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
        width: "14",
        height: "14",
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        'stroke-width': "2",
        'stroke-linecap': "round",
        'stroke-linejoin': "round",
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
        d: "M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.polyline)({
        points: "16 6 12 2 8 6",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.line)({
        x1: "12",
        y1: "2",
        x2: "12",
        y2: "15",
    });
}
/** @type {__VLS_StyleScopedClasses['header']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-title']} */ ;
/** @type {__VLS_StyleScopedClasses['conv-title-input']} */ ;
/** @type {__VLS_StyleScopedClasses['header-badges']} */ ;
/** @type {__VLS_StyleScopedClasses['status-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['status-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['header-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            editingName: editingName,
            editNameValue: editNameValue,
            nameInput: nameInput,
            copied: copied,
            startRename: startRename,
            saveRename: saveRename,
            copyUrl: copyUrl,
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
