// SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Logo Component Shim
 *
 * Renders the official Red Hat logo from the static asset
 * `public/red-hat-logo.png` (the Red Hat hat mark, transparent PNG).
 */

import { type FC } from 'react'

interface LogoProps {
  /** 'horizontal' renders a wider logo; 'logo-only' renders the hat mark */
  kind?: 'horizontal' | 'logo-only'
  size?: 'small' | 'medium' | 'large'
  className?: string
}

/** Dimensions when showing the full logo (wider aspect for horizontal layout) */
const fullSizeMap = {
  small: { width: 80, height: 44 },
  medium: { width: 120, height: 66 },
  large: { width: 160, height: 88 },
} as const

/** Dimensions when showing just the hat (matches the 132x100 asset aspect ratio) */
const hatSizeMap = {
  small: { width: 37, height: 28 },
  medium: { width: 53, height: 40 },
  large: { width: 74, height: 56 },
} as const

const RED_HAT_LOGO_SRC = '/red-hat-logo.png'

/**
 * Renders the official Red Hat logo as an <img> from the public asset.
 */
export const Logo: FC<LogoProps> = ({ kind = 'horizontal', size = 'medium', className }) => {
  const isHatOnly = kind === 'logo-only'
  const dims = isHatOnly ? hatSizeMap[size] : fullSizeMap[size]

  return (
    <span
      className={className}
      style={{ display: 'inline-flex', alignItems: 'center', width: dims.width, height: dims.height }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- small static brand asset, no optimization needed */}
      <img
        src={RED_HAT_LOGO_SRC}
        alt="Red Hat"
        width={dims.width}
        height={dims.height}
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
      />
    </span>
  )
}
