import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import ConversationPage from './pages/ConversationPage.vue'

const router = createRouter({
  history: createWebHistory('/v2/'),
  routes: [
    { path: '/', component: App },
    { path: '/c/:uid', component: ConversationPage, props: true },
  ],
})

createApp(App).use(router).mount('#app')
