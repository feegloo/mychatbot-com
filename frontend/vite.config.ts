import { defineConfig, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import { cp } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createRequire } from "node:module";

const projectDir = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
// Locate pdfjs-dist package root via its package.json entry so we resolve the
// correct install regardless of hoisting.
const pdfjsDistDir = dirname(require.resolve("pdfjs-dist/package.json"));

// pdfjs-dist v5 ships several runtime asset folders that the PDF viewer needs
// to fully render documents — most importantly `wasm/` (JPEG2000/JBIG2 image
// decoders) and `iccs/` (ICC color profiles); without them embedded images in
// PDFs fail to render. `cmaps/` (CJK) and `standard_fonts/` are included for
// correct font fallbacks.
const PDFJS_ASSET_DIRS = ["wasm", "iccs", "cmaps", "standard_fonts"] as const;

/**
 * Copies pdfjs-dist runtime assets into the dev server (served from root under
 * `/pdfjs/...`) and into the production build output.
 */
function pdfjsAssetsPlugin(): Plugin {
  const assetRoute = "/pdfjs/";
  return {
    name: "chatrag:pdfjs-assets",
    configureServer(server) {
      server.middlewares.use(assetRoute, async (req, res, next) => {
        try {
          const requestedUrl = req.url || "/";
          const cleaned = requestedUrl.split("?")[0].split("#")[0];
          const relative = decodeURIComponent(cleaned.replace(/^\/+/, ""));
          // Prevent path traversal — only serve files inside pdfjs-dist.
          if (relative.includes("..")) {
            res.statusCode = 403;
            res.end("Forbidden");
            return;
          }
          const [dir, ...rest] = relative.split("/");
          if (!PDFJS_ASSET_DIRS.includes(dir as (typeof PDFJS_ASSET_DIRS)[number])) {
            next();
            return;
          }
          const filePath = resolve(pdfjsDistDir, dir, ...rest);
          const fs = await import("node:fs/promises");
          const data = await fs.readFile(filePath);
          res.setHeader(
            "Content-Type",
            filePath.endsWith(".wasm") ? "application/wasm" : "application/octet-stream",
          );
          res.end(data);
        } catch {
          next();
        }
      });
    },
    async writeBundle(outputOptions) {
      const outDir = resolve(projectDir, outputOptions.dir ?? "dist");
      await Promise.all(
        PDFJS_ASSET_DIRS.map((name) =>
          cp(resolve(pdfjsDistDir, name), resolve(outDir, "pdfjs", name), {
            recursive: true,
          }),
        ),
      );
    },
  };
}

export default defineConfig({
  plugins: [
    vue(),
    pdfjsAssetsPlugin(),
    // Must be after all other plugins so source maps are generated correctly
    sentryVitePlugin({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      disable: !process.env.SENTRY_AUTH_TOKEN,
      sourcemaps: {
        filesToDeleteAfterUpload: ["./dist/**/*.map"],
      },
    }),
  ],
  build: {
    sourcemap: "hidden",
    rollupOptions: {
      output: {
        manualChunks: {
          sentry: ["@sentry/vue"],
        },
      },
    },
  },
  server: {
    port: 5173
  }
});
