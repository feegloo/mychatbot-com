import { createRouter, createWebHistory } from "vue-router";
import HomePage from "./pages/HomePage.vue";
import ConversationPage from "./pages/ConversationPage.vue";
import SharedMessagePage from "./pages/SharedMessagePage.vue";
import DebugTablesPage from "./pages/DebugTablesPage.vue";
import EmbedPage from "./pages/EmbedPage.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage },
    { path: "/c/:conversationId", component: ConversationPage, props: true },
    { path: "/m/:messageId", component: SharedMessagePage, props: true },
    { path: "/embed/:conversationId", component: EmbedPage, props: true, meta: { embed: true } },
    { path: "/debug", component: DebugTablesPage }
  ]
});
