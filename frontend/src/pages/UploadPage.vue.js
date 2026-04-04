import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { uploadFiles, saveConversationToken } from "../api";
onMounted(() => {
    document.title = "chatrag.app";
});
const router = useRouter();
const files = ref([]);
const dragover = ref(false);
const submitting = ref(false);
const error = ref("");
const inputRef = ref(null);
function openFilePicker() {
    inputRef.value?.click();
}
function onInputChange(event) {
    const target = event.target;
    files.value = Array.from(target.files || []);
}
function onDrop(event) {
    dragover.value = false;
    files.value = Array.from(event.dataTransfer?.files || []);
}
async function submit() {
    submitting.value = true;
    error.value = "";
    try {
        const data = await uploadFiles(files.value);
        // Save owner password (persistent token) for this conversation
        if (data.ownerPassword) {
            saveConversationToken(data.conversationId, data.ownerPassword);
        }
        router.push(data.url);
    }
    catch (err) {
        error.value = err?.response?.data?.error || err?.message || "Upload failed";
    }
    finally {
        submitting.value = false;
    }
}
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "page" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "header" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "grid grid-2" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ onDragover: (...[$event]) => {
            __VLS_ctx.dragover = true;
        } },
    ...{ onDragleave: (...[$event]) => {
            __VLS_ctx.dragover = false;
        } },
    ...{ onDrop: (__VLS_ctx.onDrop) },
    ...{ class: "dropzone" },
    ...{ class: ({ dragover: __VLS_ctx.dragover }) },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
    ...{ onChange: (__VLS_ctx.onInputChange) },
    ref: "inputRef",
    type: "file",
    multiple: true,
    ...{ style: {} },
});
/** @type {typeof __VLS_ctx.inputRef} */ ;
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.openFilePicker) },
    ...{ class: "button secondary" },
});
if (__VLS_ctx.files.length) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "file-list" },
    });
    for (const [file] of __VLS_getVForSourceType((__VLS_ctx.files))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (file.name),
            ...{ class: "file-pill" },
        });
        (file.name);
        (Math.round(file.size / 1024));
    }
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.submit) },
    ...{ class: "button" },
    disabled: (!__VLS_ctx.files.length || __VLS_ctx.submitting),
});
(__VLS_ctx.submitting ? "Uploading..." : "Upload files");
if (__VLS_ctx.error) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ style: {} },
    });
    (__VLS_ctx.error);
}
if (false) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.ol, __VLS_intrinsicElements.ol)({
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
}
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['header']} */ ;
/** @type {__VLS_StyleScopedClasses['grid']} */ ;
/** @type {__VLS_StyleScopedClasses['grid-2']} */ ;
/** @type {__VLS_StyleScopedClasses['dropzone']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['file-list']} */ ;
/** @type {__VLS_StyleScopedClasses['file-pill']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            files: files,
            dragover: dragover,
            submitting: submitting,
            error: error,
            inputRef: inputRef,
            openFilePicker: openFilePicker,
            onInputChange: onInputChange,
            onDrop: onDrop,
            submit: submit,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
