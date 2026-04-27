/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type, @typescript-eslint/no-explicit-any -- standard Vite Vue SFC shim; the `any` here matches Vue's own .d.ts.
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module '@tinymomentum/liquid-glass-vue' {
  import type { DefineComponent, Plugin } from 'vue'

  export const LiquidGlassContainer: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export const LiquidGlassButton: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export const LiquidGlassLink: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>

  const plugin: Plugin
  export default plugin
}
