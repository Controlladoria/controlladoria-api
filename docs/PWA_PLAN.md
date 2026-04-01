# PWA Conversion Plan - ControlladorIA

**Created: 2026-03-05**
**Status: PLANNING (not started)**

---

## Current State

- **Framework**: Next.js 16.1.6 (App Router)
- **Mobile**: Already responsive (hamburger menu, tap targets, safe-area padding)
- **Offline**: Zero support (no service worker, no manifest, no caching)
- **Icons**: Only `favicon.svg` and `favicon.png` exist
- **next.config.ts**: Empty (no custom config)

---

## What We Need

### Phase 1 — Minimum Viable PWA (Installable)

These are the bare minimum to pass Chrome's PWA installability criteria.

**1. Web App Manifest (`public/manifest.json`)**
- `name`: "ControlladorIA - Sistema Financeiro"
- `short_name`: "ControlladorIA"
- `start_url`: "/login"
- `display`: "standalone"
- `background_color`: white / dark
- `theme_color`: `#0d767b` (brand teal)
- `icons`: array of sizes (see #2)
- `lang`: "pt-BR"

**2. Icon Set (generate from existing logo)**
- `icon-192x192.png` (required)
- `icon-512x512.png` (required)
- `icon-maskable-192x192.png` (for Android adaptive icons)
- `icon-maskable-512x512.png`
- `apple-touch-icon-180x180.png` (iOS home screen)

**3. Service Worker (basic shell caching)**
- Cache the app shell (HTML, CSS, JS bundles)
- Cache static assets (logos, icons, fonts)
- Network-first strategy for API calls
- Offline fallback page ("Sem conexao, tente novamente")
- Use `next-pwa` package or `@serwist/next` (Next.js 16 compatible)

**4. Meta Tags in `layout.tsx`**
- `<meta name="theme-color" content="#0d767b" />`
- `<link rel="manifest" href="/manifest.json" />`
- `<meta name="apple-mobile-web-app-capable" content="yes" />`
- `<meta name="apple-mobile-web-app-status-bar-style" content="default" />`
- `<link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png" />`

**Result**: App can be installed on Android/iOS home screen, has app icon, opens in standalone mode (no browser chrome).

---

### Phase 2 — Smart Caching (Works Better Offline)

**5. Caching Strategy by Route**

| Route Type | Strategy | TTL |
|---|---|---|
| App shell (`/`, `/login`, `/dashboard`) | Cache-first | Until new deploy |
| Static assets (JS/CSS/images) | Cache-first | Until new deploy |
| API: `/auth/*` | Network-only | Never cache |
| API: `/dashboard/*` | Stale-while-revalidate | 5 min |
| API: `/documents/*` | Network-first | Fallback to cache |
| API: `/reports/*`, `/dre/*` | Stale-while-revalidate | 10 min |
| Fonts (Google Fonts) | Cache-first | 30 days |

**6. Offline Fallback Page**
- Simple branded page: "Voce esta offline"
- Show cached data if available
- Auto-retry when connection returns
- Don't block login page (just show message)

**7. Cache Invalidation on Deploy**
- Service worker versioning (auto-updates on new build)
- `skipWaiting()` + `clients.claim()` for instant activation
- Show toast: "Nova versao disponivel" with refresh button

---

### Phase 3 — App-Like Experience (Nice to Have)

**8. iOS Splash Screens**
- Apple requires specific sizes per device
- Generate with `pwa-asset-generator` tool
- Add `<link rel="apple-touch-startup-image">` tags

**9. Install Prompt (Custom)**
- Intercept `beforeinstallprompt` event
- Show branded banner: "Instalar ControlladorIA"
- Dismiss and remember choice in localStorage
- Show only after 2nd visit (avoid annoying first-timers)

**10. Background Sync for Uploads**
- Queue failed document uploads in IndexedDB
- Retry when connection returns (Background Sync API)
- Show pending upload count in sidebar badge

**11. App Shortcuts (Android)**
- Add to manifest `shortcuts` array:
  - "Upload Documento" -> `/upload`
  - "Relatorios" -> `/reports`
  - "DRE" -> `/dre-balanco`

---

## Package Options

| Package | Pros | Cons |
|---|---|---|
| `@serwist/next` | Modern, active, Next.js 16 support | Newer, less docs |
| `next-pwa` (v5+) | Most popular, well-documented | Original maintainer moved on, community fork |
| Manual (Workbox) | Full control | More work, manual config |

**Recommendation**: `@serwist/next` — built for modern Next.js, actively maintained, handles App Router well.

---

## Files to Create/Modify

### New Files
```
frontend/public/manifest.json
frontend/public/icons/icon-192x192.png
frontend/public/icons/icon-512x512.png
frontend/public/icons/icon-maskable-192x192.png
frontend/public/icons/icon-maskable-512x512.png
frontend/public/icons/apple-touch-icon-180x180.png
frontend/app/offline/page.tsx          (offline fallback)
frontend/sw.ts                         (service worker source, if using serwist)
```

### Modified Files
```
frontend/package.json                  (add @serwist/next)
frontend/next.config.ts                (wrap with serwist/PWA plugin)
frontend/app/layout.tsx                (add meta tags + manifest link)
```

---

## What We DON'T Need

- Push notifications (not relevant for financial docs system)
- Geolocation
- Camera/microphone access
- Web Share Target API
- Payment Request API (we use Stripe redirect)
- WebSocket/real-time sync (we use polling)

---

## Effort Estimate

| Phase | Work | Time |
|---|---|---|
| Phase 1 (Installable) | Manifest + icons + basic SW + meta tags | ~2 hours |
| Phase 2 (Smart Caching) | Caching strategies + offline page + cache invalidation | ~3 hours |
| Phase 3 (App-Like) | Splash screens + install prompt + upload sync | ~4 hours |
| **Total** | | **~1 day** |

---

## Pre-requisites Before Starting

1. **Generate icon set** from existing `logo.png` (need 192, 512, maskable, apple-touch)
2. **Decide**: do we want the install prompt or just silent installability?
3. **Decide**: do we need offline upload queue (Phase 3) or is offline = "show message" enough?
