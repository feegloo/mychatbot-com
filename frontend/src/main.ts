import { createApp } from "vue";
import FloatingVue from "floating-vue";
import "floating-vue/dist/style.css";
import App from "./App.vue";
import router from "./router";
import "./style.css";
import { migrateLocalData } from "./utils/localData";

migrateLocalData();
createApp(App).use(router).use(FloatingVue).mount("#app");
