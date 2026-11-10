/// <reference types="vite/client" />
interface ImportMetaEnv {
  /** Base URL of the VitalNest API. Empty means same origin (the dev server proxies /v1). */
  readonly VITE_API_BASE_URL?: string
  /** Set to "true" to hide the "Demo states" switch (for a release build). */
  readonly VITE_HIDE_DEMO?: string
  /** Cognito Hosted UI address, e.g. https://prefix.auth.ap-south-1.amazoncognito.com. Empty disables sign-in. */
  readonly VITE_COGNITO_DOMAIN?: string
  /** Cognito app client id (public). */
  readonly VITE_COGNITO_CLIENT_ID?: string
}
