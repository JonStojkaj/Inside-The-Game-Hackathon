/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_SOURCE?: 'static' | 'api'
  readonly VITE_DATA_BASE?: string
  readonly VITE_API_BASE?: string
  readonly VITE_MATCH_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
