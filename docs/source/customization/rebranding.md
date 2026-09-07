<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Rebranding the Frontend

## Overview

This guide walks through replacing the NVIDIA brand identity with your own organization's brand in the AI-Q frontend. All changes are confined to `frontends/ui/` — no backend changes needed.

The approach uses **CSS custom property overrides** rather than editing the KUI design system source directly. This means your brand colors cascade through all components automatically, and you can update the design system without losing your customizations.


## Brand Elements Summary

| Element | NVIDIA Default | Example (Red Hat) | File(s) to Edit |
|---------|---------------|-------------------|-----------------|
| Logo SVG | NVIDIA eye mark | Red Hat fedora | `src/adapters/ui/Logo.tsx` |
| Primary color | `#76b900` (green) | `#EE0000` (red) | `src/app/globals.css` |
| Font family | NVIDIA Sans (CDN) | Red Hat Display/Text | `src/app/layout.tsx`, `src/app/globals.css` |
| App name | AI-Q | Red Hat Research | `src/app/layout.tsx`, `AppBar.tsx`, `ChatArea.tsx`, `signin/page.tsx` |
| Favicon | NVIDIA `.ico` | Custom `.svg` | `public/favicon.svg`, `src/app/layout.tsx` |
| Accent colors | Green/blue tokens | Red tokens | `src/app/globals.css`, `src/styles/kui-generated.css` |


## Step 1: Replace the Logo

**File:** `frontends/ui/src/adapters/ui/Logo.tsx`

The component renders an inline SVG with two props:
- `kind`: `'horizontal'` (wider logo) or `'logo-only'` (icon mark)
- `size`: `'small'`, `'medium'`, or `'large'`

Replace the SVG `<path>` elements with your brand mark. Update the `aria-label` for accessibility and the `fill` color to match your brand.

Maintain the size maps so the logo renders correctly in all contexts:
- `fullSizeMap` — dimensions for horizontal layout (header bar)
- `eyeSizeMap` — dimensions for icon-only contexts (compact views)


## Step 2: Remap Brand Colors

**File:** `frontends/ui/src/app/globals.css`

The KUI design system uses a green color palette (`--color-green-025` through `--color-green-950`) that feeds into semantic theme tokens. Override these in an **unlayered block** (outside `@layer`) for highest cascade priority:

```css
:root {
  --color-brand: #EE0000;          /* Your primary brand color */
  --color-green-025: #fde0e0;      /* Lightest tint */
  --color-green-050: #fcc;
  --color-green-100: #f99;
  --color-green-200: #f66;
  --color-green-300: #EE0000;      /* Primary (matches --color-brand) */
  --color-green-400: #CC0000;      /* Hover state */
  --color-green-500: #A30000;      /* Selected/active state */
  --color-green-600: #8F0000;
  --color-green-700: #700;
  --color-green-800: #500;
  --color-green-900: #3C0000;
  --color-green-950: #210000;      /* Darkest shade */
}
```

The semantic tokens (`--background-color-interaction-primary-base`, `--border-color-brand`, `--text-color-brand`) reference these palette variables and will update automatically.

### Blue Accent Override

If you want info banners and input focus states to match your brand instead of staying blue, also override the blue accent tokens:

```css
:where(:root, .rh-light, .nv-light) {
  --background-color-accent-blue: var(--color-green-025);
  --border-color-accent-blue: var(--color-green-600);
  --text-color-accent-blue: var(--color-green-700);
}
:is(.rh-dark, .nv-dark) {
  --background-color-accent-blue: var(--color-green-900);
  --border-color-accent-blue: var(--color-green-300);
  --text-color-accent-blue: var(--color-green-300);
}
```

### KUI Generated CSS

Some hardcoded hex values in `src/styles/kui-generated.css` may also need updating. Search for your original brand color (e.g., `#76b900`) and replace with your new color. The blue palette (`--color-blue-*`) can similarly be remapped if needed.


## Step 3: Change Fonts

**File:** `frontends/ui/src/app/layout.tsx`

Add your font import to `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
<link
  href="https://fonts.googleapis.com/css2?family=Your+Font:wght@400;500;600;700&display=swap"
  rel="stylesheet"
/>
```

**File:** `frontends/ui/src/app/globals.css`

Apply the font site-wide:

```css
html, body, * {
  font-family: 'Your Font', system-ui, sans-serif !important;
}
```

The `!important` is needed to override NVIDIA Sans declarations in `kui-generated.css`.


## Step 4: Update App Name and Metadata

Update the application name in these locations:

| Location | File | What to change |
|----------|------|---------------|
| Page title | `src/app/layout.tsx` | `metadata.title` |
| Page description | `src/app/layout.tsx` | `metadata.description` |
| Header bar | `src/features/layout/components/AppBar.tsx` | Text inside `<Text>` component |
| Welcome message | `src/features/layout/components/ChatArea.tsx` | "Welcome to ..." text (appears twice: logged-out and logged-in states) |
| Sign-in page | `src/app/auth/signin/page.tsx` | "Sign in to ..." text |
| SSO button labels | `AppBar.tsx`, `ChatArea.tsx` | `aria-label` and `title` attributes |
| Docs link | `AppBar.tsx` | URL in `window.open(...)` |


## Step 5: Replace Favicon

**File:** `frontends/ui/public/favicon.svg`

Create your favicon as an SVG for best scaling across devices:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#EE0000"/>
  <text x="32" y="45" text-anchor="middle" font-weight="700" font-size="38" fill="white">RH</text>
</svg>
```

Update the reference in `src/app/layout.tsx`:

```typescript
icons: {
  icon: '/favicon.svg',
},
```


## Step 6: Accent Colors in Components

Some components have inline brand color references. Search for your original color hex code across the `src/` directory and update:

- **AppBar.tsx** — Sign-in button `bg-[#76b900]` and `hover:bg-[#5a8f00]`
- **ResearchPanel.tsx** — Toggle hover `hover:border-[#76B900]`
- **icons.tsx** — Generate icon `fill="#76B900"`
- **InputArea.tsx** — Input container border class


## Verification Checklist

After rebranding, verify these in both light and dark themes:

- [ ] Header bar shows your logo and app name
- [ ] Primary buttons use your brand color
- [ ] Hover and active states use your darker shade
- [ ] "Starting Deep Research" banner uses your brand color (not blue)
- [ ] Chat input border is visible in dark mode
- [ ] Sign-in page shows your branding
- [ ] Favicon appears in browser tab
- [ ] Welcome message shows your app name
- [ ] No remaining references to the original brand color hex code

## Chart colours

The inline result charts have their own palette, separate from the KUI tokens
above. It is defined in `frontends/ui/src/app/globals.css` as `--result-chart-*`,
with independently chosen light and dark values.

```css
:where(:root, .rh-light, .nv-light) {
  --result-chart-1: #EE0000;   /* series 1 -- brand colour belongs here */
  --result-chart-2: #2a78d6;
  --result-chart-3: #1baf7a;
  --result-chart-4: #eda100;
  --result-chart-neutral: #595959;
  --result-chart-gain: #2a78d6;
  --result-chart-loss: #EE0000;
}
```

Two constraints that are easy to get wrong:

- **Do not build the series slots from one hue.** A single-hue ramp (brand at
  100%, 80%, 60% ...) cannot carry categorical identity -- adjacent steps are
  indistinguishable to full-colour vision, never mind colour-blind readers.
  Use separate hues and put the brand colour on slot 1.
- **Do not use green/red for gain/loss.** That pair fails colour-blind
  separation. Blue/red is the safe diverging pair.

Series slots are named by role (`primary`, `secondary`, ...), not by hue, so a
chart can never claim to be a colour it is not. The agent prompts in
`src/aiq_agent/agents/*/prompts/` reference the same role names -- change both
together.
