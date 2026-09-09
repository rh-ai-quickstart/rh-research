// SPDX-FileCopyrightText: Copyright (c) 2026 Red Hat, Inc.
// SPDX-License-Identifier: Apache-2.0
/**
 * Guards the semantic state colours after the Red Hat palette remap.
 *
 * globals.css repaints KUI's --color-green-* palette Red Hat red so brand and
 * primary tokens turn red. KUI derives its *success* tokens from that same
 * palette, so without a dedicated override "success" silently became red and
 * indistinguishable from "danger" (connected vs error, completed vs failed).
 * A hand-edit of the generated blue palette did the same to "info". Nothing in
 * lint, type-check or the component tests can see a token chain, so this spec
 * resolves the chains the way the cascade would and pins the hue families.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

const read = (p: string): string => readFileSync(resolve(__dirname, p), 'utf8')
// Cascade order matters: kui-generated.css is @imported first (and its tokens live
// in @layer base); the unlayered Red Hat blocks in globals.css come after and win.
const CSS = read('../styles/kui-generated.css') + '\n' + read('./globals.css')

type Theme = 'light' | 'dark'
const BLOCK = /([^{}]+)\{([^{}]*)\}/g

/** Collect custom-property declarations that apply to a theme, later wins. */
const tokensFor = (theme: Theme): Map<string, string> => {
  const map = new Map<string, string>()
  for (const m of CSS.matchAll(BLOCK)) {
    const selector = m[1].trim()
    const applies =
      theme === 'light'
        ? /(^|[\s,(]):root(?![-\w])/.test(selector) || /\.(rh|nv)-light\b/.test(selector)
        : /\.(rh|nv)-dark\b/.test(selector) || /(^|[\s,(]):root(?![-\w])/.test(selector)
    if (!applies) continue
    // A :root-only block also feeds dark mode but must not beat a .*-dark block that
    // came earlier only because of file order; theme blocks always outrank :root.
    const isThemeBlock = /\.(rh|nv)-(light|dark)\b/.test(selector)
    for (const d of m[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      const [, name, value] = d
      if (!isThemeBlock && theme === 'dark' && map.has(name) && darkSet.has(name)) continue
      if (isThemeBlock && theme === 'dark') darkSet.add(name)
      map.set(name, value.trim())
    }
  }
  return map
}
const darkSet = new Set<string>()

const resolveVar = (tokens: Map<string, string>, name: string, depth = 0): string => {
  const raw = tokens.get(name)
  if (raw === undefined || depth > 12) return ''
  const ref = /^var\((--[\w-]+)(?:,\s*([^)]+))?\)$/.exec(raw)
  if (!ref) return raw
  const inner = resolveVar(tokens, ref[1], depth + 1)
  return inner || (ref[2] ?? '').trim()
}

const hexToHue = (hex: string): number | null => {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  let h = m[1]
  if (h.length === 3) h = [...h].map((c) => c + c).join('')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  if (max === min) return null
  const d = max - min
  let hue =
    max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  hue = Math.round(hue * 60)
  return hue < 0 ? hue + 360 : hue
}

const isGreen = (hue: number | null): boolean => hue !== null && hue >= 70 && hue <= 160
const isBlue = (hue: number | null): boolean => hue !== null && hue >= 185 && hue <= 250
const isRed = (hue: number | null): boolean => hue !== null && (hue <= 15 || hue >= 345)

describe.each<Theme>(['light', 'dark'])('semantic state colours (%s)', (theme) => {
  const tokens = tokensFor(theme)
  const hue = (name: string): number | null => hexToHue(resolveVar(tokens, name))

  test('success text and border resolve to a green, not the brand red', () => {
    for (const name of ['--text-color-feedback-success', '--border-color-feedback-success']) {
      const h = hue(name)
      expect(isGreen(h), `${name} resolved to hue ${h} (${resolveVar(tokens, name)})`).toBe(true)
      expect(isRed(h), `${name} must not be red`).toBe(false)
    }
  })

  test('info text and border resolve to a blue, not the brand red', () => {
    for (const name of ['--text-color-feedback-info', '--border-color-feedback-info']) {
      const h = hue(name)
      expect(isBlue(h), `${name} resolved to hue ${h} (${resolveVar(tokens, name)})`).toBe(true)
    }
  })

  test('danger stays red and differs from success', () => {
    expect(isRed(hue('--text-color-feedback-danger'))).toBe(true)
    expect(resolveVar(tokens, '--text-color-feedback-danger')).not.toBe(
      resolveVar(tokens, '--text-color-feedback-success')
    )
  })

  test('brand and primary interaction stay Red Hat red', () => {
    expect(resolveVar(tokens, '--color-brand').toLowerCase()).toBe('#ee0000')
    expect(isRed(hue('--background-color-interaction-primary-base'))).toBe(true)
  })

  test('no NVIDIA green reaches a token', () => {
    for (const [name, value] of tokens) {
      const v = resolveVar(tokens, name).toLowerCase()
      expect(v.includes('#76b900') || v.includes('#4e8500') || v.includes('#8fd400'), `${name} = ${value}`).toBe(false)
    }
  })
})
