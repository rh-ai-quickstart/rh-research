// SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'
import { CHART_COLORS } from './types'
import { CYCLE, PALETTE, seriesColor } from './palette'

/**
 * The palette's real invariants live in CSS, not in this module -- `palette.ts`
 * only holds `var()` references. Asserting on those strings is circular: it
 * cannot tell #EE0000 from #EE0000, which is exactly the defect being guarded
 * against (upstream had GAIN and LOSS resolving to the same red). So these tests
 * parse globals.css and assert on resolved hexes.
 */
const CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8')

function tokens(scope: 'light' | 'dark'): Record<string, string> {
  // Both blocks declare slot 1 identically, so key off the scope selector.
  const selector = scope === 'light' ? ':where(:root, .rh-light, .nv-light)' : ':is(.rh-dark, .nv-dark)'
  const idx = CSS.lastIndexOf(selector + ' {\n  --result-chart-1')
  expect(idx, `${scope} chart-token block not found`).toBeGreaterThan(-1)
  const block = CSS.slice(idx, CSS.indexOf('}', idx))
  const out: Record<string, string> = {}
  for (const [, k, v] of block.matchAll(/--result-chart-([a-z0-9]+):\s*(#[0-9a-fA-F]{3,6})/g)) {
    out[k] = v.toLowerCase()
  }
  return out
}

describe.each(['light', 'dark'] as const)('resolved palette (%s)', (scope) => {
  const t = tokens(scope)

  test('every cycle slot has a hex', () => {
    expect(Object.keys(t).sort()).toEqual(['1', '2', '3', '4', 'gain', 'loss', 'neutral'])
  })

  test('the four categorical slots are all visually distinct', () => {
    const series = [t['1'], t['2'], t['3'], t['4']]
    expect(new Set(series).size).toBe(4)
  })

  test('slot 1 is Red Hat red', () => {
    expect(t['1']).toBe('#ee0000')
  })

  test('GAIN and LOSS resolve to different colours', () => {
    // The upstream defect: GAIN was --color-brand and LOSS was a near-identical
    // red, so delta charts lost their polarity encoding entirely.
    expect(t.gain).not.toBe(t.loss)
  })

  test('GAIN is not a red', () => {
    // Guards the specific regression -- a red GAIN reads as a loss.
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(t.gain.slice(i, i + 2), 16))
    expect(r, `GAIN ${t.gain} is red-dominant`).toBeLessThan(Math.max(g, b))
  })
})

describe('seriesColor', () => {
  test('honors an explicit slot', () => {
    expect(seriesColor('secondary', 0)).toBe(PALETTE.secondary)
  })

  test('cycles in fixed order when unset, and wraps', () => {
    CYCLE.forEach((slot, i) => expect(seriesColor(undefined, i)).toBe(PALETTE[slot]))
    expect(seriesColor(undefined, CYCLE.length)).toBe(PALETTE[CYCLE[0]])
  })
})

describe('slot naming', () => {
  test('CYCLE covers exactly the declared colours', () => {
    expect([...CYCLE].sort()).toEqual([...CHART_COLORS].sort())
  })

  test('slots are named by role, never by hue', () => {
    // Hue names caused the defect this palette fixes: a slot called "green" that
    // painted Red Hat red, while the prompts told the model to say "green".
    for (const name of CHART_COLORS) {
      expect(name).toMatch(/^(primary|secondary|tertiary|quaternary|neutral)$/)
    }
  })
})
