/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type, @typescript-eslint/no-explicit-any -- standard Vite Vue SFC shim; the `any` here matches Vue's own .d.ts.
  const component: DefineComponent<{}, {}, any>
  export default component
}
