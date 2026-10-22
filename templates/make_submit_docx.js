// 生成 GeoNews 街闻 投稿表.docx
// 原则：给外部投稿人看，短、能一眼扫完。一行提示，不写理由、不写铺垫。
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
  BorderStyle, convertInchesToTwip,
} = require("docx");

const FONT = "微软雅黑";
const INK = "1A1A1A";
const HINT = "8A8A8A";

const blank = (n = 3) =>
  Array.from({ length: n }, () =>
    new Paragraph({
      spacing: { before: 160, after: 0 },
      children: [new TextRun({ text: " ", font: FONT, size: 22 })],
    })
  );

let q = 0;
const field = (label, hint, fill) => {
  q += 1;
  const out = [
    new Paragraph({
      spacing: { before: 360, after: 40 },
      children: [new TextRun({ text: `${q}. ${label}`, font: FONT, size: 24, bold: true, color: INK })],
    }),
  ];
  if (hint) {
    out.push(new Paragraph({
      spacing: { before: 0, after: 60 },
      children: [new TextRun({ text: hint, font: FONT, size: 19, color: HINT })],
    }));
  }
  out.push(...fill());
  return out;
};

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 22, color: INK } } } },
  sections: [
    {
      properties: {
        page: {
          margin: {
            top: convertInchesToTwip(0.9), bottom: convertInchesToTwip(0.9),
            left: convertInchesToTwip(1.0), right: convertInchesToTwip(1.0),
          },
        },
      },
      children: [
        new Paragraph({
          spacing: { after: 320 },
          children: [new TextRun({ text: "GeoNews 街闻 投稿表", font: FONT, size: 36, bold: true, color: INK })],
        }),
        new Paragraph({
          spacing: { before: 0, after: 0 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" } },
          children: [new TextRun({ text: "你的昵称： ", font: FONT, size: 22, color: INK })],
        }),

        ...field("一句话概括", "例：「阿拉斯加今年夏季更新很多红色皮卡街景」。", () => blank(2)),
        ...field("具体陈述", "选填。", () => blank(5)),
        ...field("出处", "链接或其他形式。必填。", () => blank(2)),
        ...field("截图/录屏", "不用放这里，单独发即可。", () => blank(1)),
        ...field("其他备注", null, () => blank(2)),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = process.argv[2] || "投稿模板.docx";
  fs.writeFileSync(out, buf);
  console.log("已生成:", out, buf.length, "字节");
});
