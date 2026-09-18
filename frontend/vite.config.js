import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.DOCKER_ENV === "true" ? "http://backend:8000" : "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  // `npm test`. Only the parts with logic worth checking are covered: the
  // background-run polling, the words the sign-off queue puts on screen and
  // the paged log reader. Styling and layout are not tested.
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
    restoreMocks: true,
  },
});
