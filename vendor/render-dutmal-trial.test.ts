import { it } from "node:test"
import assert from "node:assert/strict"
import JSZip from "jszip"
import { renderHwpxToSvg } from "../src/render/index.js"
import { createXmlParser } from "../src/hwpx/parser-shared.js"
import { buildPara, prepareDeletedRanges } from "../src/render/para-model.js"

const ns = 'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
const ruby = '<hp:dutmal posType="TOP" szRatio="50" align="CENTER"><hp:mainText>확인기록</hp:mainText><hp:subText>가상 사례</hp:subText></hp:dutmal>'
it("keeps the ruby main text and annotation in an eight-slot control", () => {
  const d = createXmlParser().parseFromString(`<hp:p ${ns}><hp:run charPrIDRef="0">${ruby}<hp:t> 뒤</hp:t></hp:run></hp:p>`, "text/xml")
  const p = buildPara(d.documentElement as unknown as Element)
  assert.equal(p.chars.length, 10)
  assert.equal(p.chars[0].ctrlText, "확인기록")
  assert.equal(p.chars[0].ruby?.text, "가상 사례")
})
it("does not expose deleted ruby content", () => {
  const d = createXmlParser().parseFromString(`<hs:sec ${ns}><hp:p><hp:run><hp:deleteBegin/>${ruby}<hp:deleteEnd/></hp:run></hp:p></hs:sec>`, "text/xml")
  prepareDeletedRanges(d.documentElement as unknown as Element)
  const m = buildPara(d.getElementsByTagName("hp:p")[0] as unknown as Element)
  assert.ok(!m.chars.some(c => c.ruby || c.ctrlText))
})
async function render(control: string, height = 10000) {
  const z = new JSZip()
  z.file("Contents/header.xml", `<hh:head ${ns}><hh:fontfaces><hh:fontface lang="HANGUL"><hh:font id="0" face="휴먼명조"/></hh:fontface></hh:fontfaces><hh:charProperties><hh:charPr id="0" height="1000"><hh:fontRef hangul="0"/><hh:bold/></hh:charPr></hh:charProperties><hh:paraProperties><hh:paraPr id="0"><hh:align horizontal="LEFT"/><hh:lineSpacing type="PERCENT" value="160"/></hh:paraPr></hh:paraProperties></hh:head>`)
  z.file("Contents/section0.xml", `<hs:sec ${ns}><hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:secPr><hp:pagePr width="16000" height="${height}"><hp:margin top="0" bottom="0" left="0" right="0" header="0" footer="0"/></hp:pagePr></hp:secPr><hp:t>앞 </hp:t>${control}<hp:t> 뒤</hp:t></hp:run></hp:p><hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>후속</hp:t></hp:run></hp:p></hs:sec>`)
  return renderHwpxToSvg(await z.generateAsync({type:"uint8array"}), {reflow:true})
}
it("renders both texts, preserves spaces and reserves annotation height", async () => {
  const plain = await render('<hp:t>확인기록</hp:t>'), annotated = await render(ruby)
  assert.match(annotated.svg, />확인기록<\/text>/)
  assert.match(annotated.svg, />가상 사례<\/text>/)
  assert.match(annotated.svg, /white-space:pre/)
  const y = (s: string) => Number(s.match(/<text x="[^"]+" y="([^"]+)"[^>]*>후속<\/text>/)?.[1])
  assert.ok(y(annotated.svg) > y(plain.svg), "annotation must move following content, not just overlay it")
  assert.match(annotated.svg, /font-weight="bold"/)
})
it("counts ruby height when content crosses the page boundary", async () => {
  const plain = await render('<hp:t>확인기록</hp:t>', 2700), annotated = await render(ruby, 2700)
  assert.ok(annotated.pageCount > plain.pageCount, `${plain.pageCount} -> ${annotated.pageCount}`)
})
