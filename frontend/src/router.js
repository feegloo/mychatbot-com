import { createRouter, createWebHistory } from "vue-router";
import UploadPage from "./pages/UploadPage.vue";
import ConversationPage from "./pages/ConversationPage.vue";
export default createRouter({
    history: createWebHistory(),
    routes: [
        { path: "/", component: UploadPage },
        { path: "/c/:conversationId", component: ConversationPage, props: true }
    ]
});
