// SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChartColor } from './types'

/**
 * Categorical series slots, named by ROLE rather than by hue.
 *
 * Hue names were removed deliberately. Upstream mapped a slot called `green` to
 * `var(--color-brand)`, which is `#EE0000` in this fork -- so charts painted a
 * "green" series Red Hat red, and the agent prompts told the model to describe
 * it as green. Naming slots by role makes that class of mismatch impossible.
 *
 * The hexes live in globals.css (`--result-chart-*`) so light and dark are
 * selected independently. They are a validated categorical palette -- lightness
 * band, chroma floor, CVD separation, normal-vision floor and contrast all pass
 * in BOTH modes. Do not change a value without re-running the checker.
 *
 * Slot 1 is Red Hat red: brand identity belongs on the first series.
 */
export const PALETTE: Record<ChartColor, string> = {
  primary: 'var(--result-chart-1, #EE0000)',
  secondary: 'var(--result-chart-2, #2a78d6)',
  tertiary: 'var(--result-chart-3, #1baf7a)',
  quaternary: 'var(--result-chart-4, #eda100)',
  neutral: 'var(--result-chart-neutral, #595959)',
}

/** Fixed assignment order when a series omits an explicit color. */
export const CYCLE: ChartColor[] = ['primary', 'secondary', 'tertiary', 'quaternary', 'neutral']

/**
 * Diverging colors for delta charts; gain/loss is also encoded by bar direction.
 *
 * Blue/red, not green/red: green-vs-red fails colorblind separation outright
 * (deltaE 4.1 deuteranopia, against a floor of 8), which is the single most common
 * accessibility defect in financial charts.
 */
export const GAIN = 'var(--result-chart-gain, #2a78d6)'
export const LOSS = 'var(--result-chart-loss, #EE0000)'

/** Resolve the color for series `index`, honoring its explicit color or cycling. */
export function seriesColor(color: ChartColor | undefined, index: number): string {
  return PALETTE[color ?? CYCLE[index % CYCLE.length]]
}
