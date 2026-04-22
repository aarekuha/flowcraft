import { createRouter, createWebHistory } from "vue-router";

import BrigadierMonitoringPage from "@/pages/brigadier-monitoring/BrigadierMonitoringPage.vue";
import WorkerHomePage from "@/pages/worker-home/WorkerHomePage.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "worker-home",
      component: WorkerHomePage,
    },
    {
      path: "/monitoring",
      name: "brigadier-monitoring",
      component: BrigadierMonitoringPage,
    },
  ],
});
