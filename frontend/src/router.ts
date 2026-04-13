import { createRouter, createWebHistory } from "vue-router";
import UploadPage from "./pages/UploadPage.vue";
import ConversationPage from "./pages/ConversationPage.vue";
import SharedMessagePage from "./pages/SharedMessagePage.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: UploadPage },
    { path: "/c/:conversationId", component: ConversationPage, props: true },
    { path: "/m/:messageId", component: SharedMessagePage, props: true }
  ]
});
