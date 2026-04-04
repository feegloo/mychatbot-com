import { ref } from "vue";
import { uploadMoreFiles, requestUploadAccess, getUploadAccessRequest, approveUploadAccess, saveConversationToken } from "../api";
import { cleanFileName } from "../utils/text";
const props = defineProps();
const emit = defineEmits();
const uploadingMore = ref(false);
const uploadError = ref("");
const moreFiles = ref([]);
const moreFilesInput = ref(null);
const requestingAccess = ref(false);
const displayName = ref("");
const pendingRequestId = ref(localStorage.getItem(`pending-access-request:${props.conversationId}`) || "");
function onMoreFilesChange(event) {
    const target = event.target;
    moreFiles.value = Array.from(target.files || []);
    uploadError.value = "";
}
async function uploadMore() {
    if (!moreFiles.value.length)
        return;
    uploadingMore.value = true;
    try {
        await uploadMoreFiles(props.conversationId, moreFiles.value);
        moreFiles.value = [];
        if (moreFilesInput.value)
            moreFilesInput.value.value = "";
        emit("reload");
    }
    catch (err) {
        if (err.response?.status === 409) {
            const names = (err.response.data?.duplicates || []).join(", ");
            uploadError.value = names ? `File ${names} already uploaded` : "File already uploaded";
            moreFiles.value = [];
            if (moreFilesInput.value)
                moreFilesInput.value.value = "";
        }
        else {
            throw err;
        }
    }
    finally {
        uploadingMore.value = false;
    }
}
async function requestAccess() {
    requestingAccess.value = true;
    try {
        const response = await requestUploadAccess(props.conversationId, displayName.value);
        pendingRequestId.value = response.requestId;
        localStorage.setItem(`pending-access-request:${props.conversationId}`, response.requestId);
    }
    finally {
        requestingAccess.value = false;
    }
}
async function pollAccessRequest() {
    if (!pendingRequestId.value)
        return;
    const response = await getUploadAccessRequest(props.conversationId, pendingRequestId.value);
    if (response.status === "approved" && response.editorPassword) {
        saveConversationToken(props.conversationId, response.editorPassword);
        localStorage.removeItem(`pending-access-request:${props.conversationId}`);
        pendingRequestId.value = "";
        emit("reload");
    }
}
async function approveRequest(requestId) {
    await approveUploadAccess(props.conversationId, requestId);
    emit("reload");
}
const __VLS_exposed = { pollAccessRequest };
defineExpose(__VLS_exposed);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
    ...{ class: "card" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({
    ...{ style: {} },
});
if (__VLS_ctx.canUpload) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.canUpload))
                    return;
                __VLS_ctx.moreFilesInput?.click();
            } },
        ...{ class: "button" },
        ...{ style: {} },
    });
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
for (const [file] of __VLS_getVForSourceType((__VLS_ctx.status.files))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        key: (file.id),
        ...{ class: "file-pill" },
        ...{ style: {} },
    });
    (__VLS_ctx.cleanFileName(file.originalName));
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
    ...{ onChange: (__VLS_ctx.onMoreFilesChange) },
    ref: "moreFilesInput",
    type: "file",
    multiple: true,
    ...{ style: {} },
});
/** @type {typeof __VLS_ctx.moreFilesInput} */ ;
if (__VLS_ctx.moreFiles.length || __VLS_ctx.uploadError) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ style: {} },
    });
    if (__VLS_ctx.uploadError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ style: {} },
        });
        (__VLS_ctx.uploadError);
    }
    if (__VLS_ctx.moreFiles.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "file-list" },
        });
        for (const [file] of __VLS_getVForSourceType((__VLS_ctx.moreFiles))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (file.name),
                ...{ class: "file-pill" },
                ...{ style: {} },
            });
            (file.name);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.uploadMore) },
            ...{ class: "button" },
            ...{ style: {} },
            disabled: (__VLS_ctx.uploadingMore || !__VLS_ctx.moreFiles.length),
        });
        (__VLS_ctx.uploadingMore ? "Uploading..." : "Upload");
    }
}
if (!__VLS_ctx.canUpload) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({
        ...{ style: {} },
    });
    if (__VLS_ctx.pendingRequestId) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ style: {} },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            placeholder: "Your name",
            ...{ style: {} },
        });
        (__VLS_ctx.displayName);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.requestAccess) },
            ...{ class: "button" },
            ...{ style: {} },
            disabled: (__VLS_ctx.requestingAccess || !__VLS_ctx.displayName),
        });
        (__VLS_ctx.requestingAccess ? "Requesting..." : "Request access");
    }
}
if (__VLS_ctx.status.role === 'owner' && __VLS_ctx.status.accessRequests.length > 0) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({
        ...{ style: {} },
    });
    for (const [req] of __VLS_getVForSourceType((__VLS_ctx.status.accessRequests))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (req.id),
            ...{ style: {} },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ style: {} },
        });
        (req.displayName);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ style: {} },
        });
        (req.status);
        if (req.status === 'pending') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.status.role === 'owner' && __VLS_ctx.status.accessRequests.length > 0))
                            return;
                        if (!(req.status === 'pending'))
                            return;
                        __VLS_ctx.approveRequest(req.id);
                    } },
                ...{ class: "button" },
                ...{ style: {} },
            });
        }
    }
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
for (const [q] of __VLS_getVForSourceType((__VLS_ctx.status.suggestedQuestions))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.$emit('select-question', q);
            } },
        key: (q),
        ...{ class: "question-pill" },
        ...{ style: {} },
    });
    (q);
}
if (__VLS_ctx.status.status === 'processing') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "typing-dots" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
}
/** @type {__VLS_StyleScopedClasses['card']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['file-pill']} */ ;
/** @type {__VLS_StyleScopedClasses['file-list']} */ ;
/** @type {__VLS_StyleScopedClasses['file-pill']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['button']} */ ;
/** @type {__VLS_StyleScopedClasses['question-pill']} */ ;
/** @type {__VLS_StyleScopedClasses['typing-dots']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            cleanFileName: cleanFileName,
            uploadingMore: uploadingMore,
            uploadError: uploadError,
            moreFiles: moreFiles,
            moreFilesInput: moreFilesInput,
            requestingAccess: requestingAccess,
            displayName: displayName,
            pendingRequestId: pendingRequestId,
            onMoreFilesChange: onMoreFilesChange,
            uploadMore: uploadMore,
            requestAccess: requestAccess,
            approveRequest: approveRequest,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {
            ...__VLS_exposed,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
; /* PartiallyEnd: #4569/main.vue */
