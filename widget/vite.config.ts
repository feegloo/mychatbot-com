import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      name: "ChatRAG",
      fileName: "chatrag-widget",
      formats: ["es", "umd"],
    },
    rollupOptions: {
      output: {
        assetFileNames: "chatrag-widget.[ext]",
      },
    },
    minify: true,
    sourcemap: true,
  },
});
