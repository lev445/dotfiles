#!/usr/bin/env node
/**
 * md3-dump.mjs — «печка» для генерации эталонных MD3-палитр.
 *
 * Использует ОФИЦИАЛЬНУЮ библиотеку Material Color Utilities
 * (@material/material-color-utilities) — тот же движок, что стоит за
 * Material Theme Builder, Android `MaterialTheme` и material-web.
 *
 *   Схема:  SchemeTonalSpot / SchemeContent / SchemeMonochrome (DynamicScheme)
 *   Роли:   MaterialDynamicColors (md.sys.color.*)
 *   Тоны:   TonalPalette 0..100 (md.ref.palette.*)
 *
 * Результат (JSON) вшивается в tools/md3_theme.py как офлайн-датасет, чтобы
 * GUI и bspwmrc не зависели от node/npm на машине пользователя.
 *
 * Запуск (нужен только один раз, при изменении датасета):
 *   npm i @material/material-color-utilities@0.3.0
 *   node tools/md3-dump.mjs > tools/md3_palettes.json
 */
import {
  argbFromHex,
  hexFromArgb,
  Hct,
  MaterialDynamicColors,
  SchemeTonalSpot,
  SchemeContent,
  SchemeMonochrome,
  CorePalette,
} from '@material/material-color-utilities'

const SEEDS = [
  '#6750A4', // M3 baseline (purple)
  '#006A6A', // teal
  '#1B6EF3', // blue
  '#006874', // cyan
  '#2E6B2F', // green
  '#8B5000', // amber / brown
  '#B3261E', // red
  '#7D5260', // rose
  '#4F5B92', // indigo
  '#5B5B5B', // graphite (near-monochrome)
]

const SCHEMES = {
  'tonal-spot': SchemeTonalSpot,
  content: SchemeContent,
  monochrome: SchemeMonochrome,
}

const CONTRASTS = { standard: 0.0, medium: 0.5, high: 1.0 }

// В MCU 0.3.x роли объявлены как СТАТИЧЕСКИЕ свойства класса
const MDC = MaterialDynamicColors
const ROLE_NAMES = Object.getOwnPropertyNames(MDC).filter(
  (k) => MDC[k] && typeof MDC[k] === 'object' && typeof MDC[k].getArgb === 'function',
)
// служебные роли-«key color» в конфиг WM не нужны
const ROLES = ROLE_NAMES.filter((r) => !r.endsWith('PaletteKeyColor'))

const PALETTES = ['primary', 'secondary', 'tertiary', 'neutral', 'neutralVariant', 'error']

function schemeFor (seedHex, schemeName, isDark, contrast) {
  const hct = Hct.fromInt(argbFromHex(seedHex))
  return new SCHEMES[schemeName](hct, isDark, contrast)
}

const out = {
  meta: {
    generator: '@material/material-color-utilities@0.3.0',
    rolesSource: 'MaterialDynamicColors (md.sys.color.*)',
    generatedAt: new Date().toISOString().slice(0, 10),
    roleCount: ROLES.length,
  },
  roles: ROLES,
  schemes: {},
  palettes: {},
}

for (const seed of SEEDS) {
  // tonal-spot — для всех сидов и уровней контраста (это дефолтная M3-схема);
  // content/monochrome — только для baseline-сида, чтобы не раздувать датасет.
  const schemeNames =
    seed === SEEDS[0] ? Object.keys(SCHEMES) : ['tonal-spot']
  const contrastNames =
    seed === SEEDS[0] ? Object.keys(CONTRASTS) : ['standard']
  for (const schemeName of schemeNames) {
    const Scheme = SCHEMES[schemeName]
    for (const contrastName of contrastNames) {
      const contrast = CONTRASTS[contrastName]
      // monochrome не чувствителен к контрасту так же — но считаем всё равно
      for (const isDark of [true, false]) {
        const key = `${schemeName}|${contrastName}|${isDark ? 'dark' : 'light'}`
        let scheme
        try {
          scheme = schemeFor(seed, schemeName, isDark, contrast)
        } catch (e) {
          continue
        }
        const roles = {}
        for (const r of ROLES) {
          try {
            roles[r] = hexFromArgb(MDC[r].getArgb(scheme))
          } catch (e) {
            roles[r] = null
          }
        }
        out.schemes[seed.toUpperCase()] ??= {}
        out.schemes[seed.toUpperCase()][key] = roles
      }
    }
  }

  // Тональные палитры (md.ref.palette.*) — нужны для терминала и превью
  const cp = CorePalette.of(argbFromHex(seed))
  const map = {
    primary: cp.a1,
    secondary: cp.a2,
    tertiary: cp.a3,
    neutral: cp.n1,
    neutralVariant: cp.n2,
    error: cp.error,
  }
  out.palettes[seed.toUpperCase()] = {}
  for (const p of PALETTES) {
    const tones = {}
    for (let t = 0; t <= 100; t += 1) tones[t] = hexFromArgb(map[p].tone(t))
    out.palettes[seed.toUpperCase()][p] = tones
  }
}

// HCT-координаты сидов (для подписей в GUI)
out.seedHct = {}
for (const seed of SEEDS) {
  const h = Hct.fromInt(argbFromHex(seed))
  out.seedHct[seed.toUpperCase()] = {
    hue: +h.hue.toFixed(2),
    chroma: +h.chroma.toFixed(2),
    tone: +h.tone.toFixed(2),
  }
}

process.stdout.write(JSON.stringify(out))
