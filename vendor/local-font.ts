import { readFileSync } from "node:fs"
import { join } from "node:path"

// A locally installed face is loaded explicitly as regular so Chromium can
// synthesize bold. Registry-selected Human Myeongjo ignores bold on this host.
// No proprietary font is bundled or downloaded. Missing fonts keep the fallback.
let cached: string | undefined
export function localHumanFontCss(): string {
  if (cached !== undefined) return cached
  cached = ""
  if (process.platform !== "win32") return cached
  try {
    const b = readFileSync(join(process.env.SystemRoot ?? "C:\\Windows", "Fonts", "HMKMM.TTF"))
    if (b.length > 20_000_000 || b.readUInt32BE(0) !== 0x00010000) return cached
    cached = `@font-face{font-family:'Kordoc Local Human';src:url(data:font/ttf;base64,${b.toString("base64")}) format('truetype');font-weight:400;font-style:normal}`
  } catch { /* Other platforms / machines without the licensed face use fallback. */ }
  return cached
}
