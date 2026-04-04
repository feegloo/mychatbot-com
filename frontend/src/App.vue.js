import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import ConversationNav from "./components/ConversationNav.vue";
const sidebarOpen = ref(false);
const route = useRoute();
watch(() => route.path, () => { sidebarOpen.value = false; });
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "app-layout" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.sidebarOpen = false;
        } },
    ...{ class: "sidebar-overlay" },
    ...{ class: ({ open: __VLS_ctx.sidebarOpen }) },
});
/** @type {[typeof ConversationNav, ]} */ ;
// @ts-ignore
const __VLS_0 = __VLS_asFunctionalComponent(ConversationNav, new ConversationNav({
    ...{ 'onNavigate': {} },
    ...{ class: ({ open: __VLS_ctx.sidebarOpen }) },
}));
const __VLS_1 = __VLS_0({
    ...{ 'onNavigate': {} },
    ...{ class: ({ open: __VLS_ctx.sidebarOpen }) },
}, ...__VLS_functionalComponentArgsRest(__VLS_0));
let __VLS_3;
let __VLS_4;
let __VLS_5;
const __VLS_6 = {
    onNavigate: (...[$event]) => {
        __VLS_ctx.sidebarOpen = false;
    }
};
var __VLS_2;
__VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
    ...{ class: "app-main" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.sidebarOpen = !__VLS_ctx.sidebarOpen;
        } },
    ...{ class: "sidebar-toggle" },
    'aria-label': "Toggle menu",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
    width: "22",
    height: "22",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    'stroke-width': "2",
    'stroke-linecap': "round",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.line)({
    x1: "3",
    y1: "6",
    x2: "21",
    y2: "6",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.line)({
    x1: "3",
    y1: "12",
    x2: "21",
    y2: "12",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.line)({
    x1: "3",
    y1: "18",
    x2: "21",
    y2: "18",
});
const __VLS_7 = {}.RouterView;
/** @type {[typeof __VLS_components.RouterView, typeof __VLS_components.routerView, ]} */ ;
// @ts-ignore
const __VLS_8 = __VLS_asFunctionalComponent(__VLS_7, new __VLS_7({
    key: (__VLS_ctx.$route.fullPath),
}));
const __VLS_9 = __VLS_8({
    key: (__VLS_ctx.$route.fullPath),
}, ...__VLS_functionalComponentArgsRest(__VLS_8));
/** @type {__VLS_StyleScopedClasses['app-layout']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['app-main']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar-toggle']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            ConversationNav: ConversationNav,
            sidebarOpen: sidebarOpen,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
