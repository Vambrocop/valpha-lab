const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat, ExternalHyperlink,
  PageBreak
} = require('docx');
const fs = require('fs');

// ── colours ──────────────────────────────────────────────────────────────────
const C = {
  navy:   '1F3864',
  blue:   '2E75B6',
  light:  'D5E8F0',
  green:  'E2EFDA',
  yellow: 'FFF2CC',
  red:    'FFE0E0',
  grey:   'F2F2F2',
  white:  'FFFFFF',
  dark:   '1A1A2E',
};

// ── helpers ───────────────────────────────────────────────────────────────────
const border = (color = 'CCCCCC') => ({ style: BorderStyle.SINGLE, size: 1, color });
const borders = (color = 'CCCCCC') => ({ top: border(color), bottom: border(color), left: border(color), right: border(color) });
const cellMargins = { top: 100, bottom: 100, left: 150, right: 150 };

function hdr(text, lvl = HeadingLevel.HEADING_1, color = C.navy) {
  return new Paragraph({
    heading: lvl,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, bold: true, color, font: 'Arial',
      size: lvl === HeadingLevel.HEADING_1 ? 32 : lvl === HeadingLevel.HEADING_2 ? 28 : 24 })],
  });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text, font: 'Arial', size: 22, ...opts })],
  });
}

function bold(text, color) {
  return new TextRun({ text, bold: true, font: 'Arial', size: 22, ...(color ? { color } : {}) });
}
function normal(text) {
  return new TextRun({ text, font: 'Arial', size: 22 });
}

function mixed(...runs) {
  return new Paragraph({ spacing: { before: 60, after: 60 }, children: runs });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: 'Arial', size: 22 })],
  });
}

function divider(color = C.blue) {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color, space: 1 } },
    spacing: { before: 160, after: 160 },
    children: [],
  });
}

function spacer() {
  return new Paragraph({ spacing: { before: 80, after: 80 }, children: [] });
}

// ── table builder ─────────────────────────────────────────────────────────────
// colWidths: array of DXA values (must sum to ~9360 for A4 content width)
function makeCell(text, fill, isHeader, width) {
  return new TableCell({
    borders: borders('AAAAAA'),
    width: { size: width, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: cellMargins,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: AlignmentType.LEFT,
      children: [new TextRun({
        text, font: 'Arial', size: 20,
        bold: isHeader, color: isHeader ? C.white : '1A1A1A',
      })],
    })],
  });
}

function makeTable(headers, rows, colWidths, headerFill = C.navy) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => makeCell(h, headerFill, true, colWidths[i])),
  });

  const dataRows = rows.map((row, ri) => {
    const fill = ri % 2 === 0 ? C.white : C.grey;
    return new TableRow({
      children: row.map((cell, i) => makeCell(cell, fill, false, colWidths[i])),
    });
  });

  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [headerRow, ...dataRows],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  DOCUMENT
// ─────────────────────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: 'bullets',
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: { document: { run: { font: 'Arial', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 36, bold: true, font: 'Arial', color: C.navy },
        paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 28, bold: true, font: 'Arial', color: C.blue },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, font: 'Arial', color: C.navy },
        paragraph: { spacing: { before: 180, after: 90 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 }, // 2cm margins
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.blue, space: 1 } },
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: '美股投资分析报告  |  2026年6月', font: 'Arial', size: 18, color: '666666' })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: C.blue, space: 1 } },
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: '仅供参考，不构成投资建议   |   第 ', font: 'Arial', size: 16, color: '888888' }),
            new TextRun({ children: [PageNumber.CURRENT], font: 'Arial', size: 16, color: '888888' }),
            new TextRun({ text: ' 页', font: 'Arial', size: 16, color: '888888' }),
          ],
        })],
      }),
    },

    children: [

      // ══════════════════════════════════════════════════════════════════════
      //  封面
      // ══════════════════════════════════════════════════════════════════════
      new Paragraph({ spacing: { before: 1200, after: 120 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: '美股投资分析报告', font: 'Arial', size: 64, bold: true, color: C.navy })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 120 },
        children: [new TextRun({ text: 'US Stock Investment Analysis', font: 'Arial', size: 32, color: C.blue, italics: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 240, after: 80 },
        children: [new TextRun({ text: '报告日期：2026年6月2日', font: 'Arial', size: 24, color: '555555' })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 80 },
        children: [new TextRun({ text: '汇率：AUD 1 = USD 0.716', font: 'Arial', size: 22, color: '888888' })] }),
      divider(C.blue),

      // 免责声明框
      new Table({
        width: { size: 9638, type: WidthType.DXA },
        columnWidths: [9638],
        rows: [new TableRow({ children: [new TableCell({
          borders: borders(C.blue),
          shading: { fill: C.light, type: ShadingType.CLEAR },
          margins: { top: 150, bottom: 150, left: 200, right: 200 },
          width: { size: 9638, type: WidthType.DXA },
          children: [
            new Paragraph({ children: [new TextRun({ text: '免责声明', font: 'Arial', size: 22, bold: true, color: C.navy })] }),
            new Paragraph({ spacing: { before: 80 }, children: [new TextRun({
              text: '本报告仅供教育参考用途，不构成任何投资建议。股市有风险，投资须谨慎。报告所引用数据截至2026年6月，价格数据实时变化，请以实际行情为准。未来收益预测均为框架性估算，不代表实际回报。投资前请咨询持牌理财顾问。',
              font: 'Arial', size: 20, color: '444444',
            })] }),
          ],
        })]})],
      }),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第一部分：估值指标说明
      // ══════════════════════════════════════════════════════════════════════
      hdr('一、核心估值指标说明', HeadingLevel.HEADING_1),
      divider(),

      hdr('1.1  市盈率（P/E）vs 市销率（P/S）', HeadingLevel.HEADING_2),
      mixed(bold('市盈率 P/E'), normal(' = 股价 ÷ 每股净利润（真正赚到的钱）')),
      mixed(bold('市销率 P/S'), normal(' = 股价 ÷ 每股营收（收款机收到的全部钱，不看成本）')),
      spacer(),

      makeTable(
        ['指标', '计算公式', '适用场景', '风险提示'],
        [
          ['市盈率 P/E', '股价 ÷ 净利润/股', '有稳定盈利的成熟公司', 'P/E低不代表便宜，烂生意P/E=8也贵'],
          ['市销率 P/S', '股价 ÷ 营收/股', '暂时亏损但高速增长', 'P/S低但一直亏损 = 危险'],
          ['PEG比率', 'P/E ÷ 年盈利增速%', '成长股估值调整', 'PEG<1便宜，PEG>2偏贵'],
          ['远期P/E', '股价 ÷ 下年预测EPS', '对比现在vs未来盈利能力', '依赖分析师预测，可能不准'],
        ],
        [2200, 2500, 2600, 2338],
      ),
      spacer(),

      hdr('1.2  推荐指数说明', HeadingLevel.HEADING_2),
      para('推荐指数（满分10分）综合考虑护城河质量、当前估值合理性、成长前景和风险四个维度打分。'),
      para('注意：推荐指数衡量的是「值不值得长期持有」，而非「短期会不会涨」。'),

      makeTable(
        ['推荐指数', '含义', '适合人群'],
        [
          ['9.0 – 10.0', '极度推荐，高质量低估值', '所有投资者'],
          ['8.0 – 8.9', '强烈推荐，质量好估值合理', '稳健型投资者'],
          ['7.0 – 7.9', '推荐，但有一定风险或估值略高', '有一定承受能力'],
          ['6.0 – 6.9', '谨慎推荐，风险较高', '进取型，小仓位'],
          ['5.9及以下', '不推荐目前价格买入，等回调', '高风险投机者'],
        ],
        [1800, 4200, 3638],
      ),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第二部分：四大类股票
      // ══════════════════════════════════════════════════════════════════════
      hdr('二、四大类股票深度分析', HeadingLevel.HEADING_1),
      divider(),

      // ── 保守稳健型 ──────────────────────────────────────────────────────
      hdr('2.1  保守稳健型', HeadingLevel.HEADING_2),
      para('核心逻辑：宽护城河 + 定价权 + 抗衰退 + 股息成长。适合第一次投资、不想担心股票每天涨跌的人。'),
      spacer(),

      makeTable(
        ['股票', '现价(USD)', 'P/E', '分析师12月目标', '上行%', '3年区间', '风险', '推荐指数'],
        [
          ['BRK.B  巴菲特公司', '$473', '17x', '~$530', '+12%', '$600–720', '⭐ 极低', '8.5 / 10'],
          ['PG  宝洁', '$147', '22x', '~$165', '+12%', '$175–210', '⭐ 极低', '8.0 / 10'],
          ['V  Visa', '$327', '30x', '~$380', '+16%', '$420–520', '⭐⭐ 低', '8.8 / 10'],
        ],
        [1700, 1200, 900, 1700, 900, 1300, 1000, 1038],
      ),
      spacer(),

      hdr('BRK.B — 巴菲特的公司本身', HeadingLevel.HEADING_3),
      bullet('护城河：保险浮存金机器 + 多元化子公司组合，无法复制的60年积累'),
      bullet('现金储备超$3,000亿，任何危机都是它的机会'),
      bullet('Greg Abel已接班，文化基因传承完整'),
      bullet('风险：体量过大，很难找到"移动针头"的超额收益机会'),

      spacer(),
      hdr('PG — 宝洁公司', HeadingLevel.HEADING_3),
      bullet('护城河：Tide、Gillette、Pampers等50+个十亿美元品牌矩阵'),
      bullet('连续67年以上提高股息，Dividend King称号'),
      bullet('通胀期间成功涨价并保住利润率，真实定价权的证明'),
      bullet('风险：增速较慢（年约5-8%），不适合追求快速增长的投资者'),

      spacer(),
      hdr('V — Visa', HeadingLevel.HEADING_3),
      bullet('护城河：全球支付网络效应（更多商家→更多持卡人→更多商家，循环加强）'),
      bullet('不承担信用风险，只收手续费，商业模式近乎完美'),
      bullet('ROIC约45-50%，全美股顶级水平，近乎无形资本投入'),
      bullet('风险：监管压力，加密货币/CBDC长期潜在威胁（10年内影响有限）'),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 成长潜力型 ──────────────────────────────────────────────────────
      hdr('2.2  成长潜力型', HeadingLevel.HEADING_2),
      para('核心逻辑：护城河 + AI/云时代的结构性成长红利。质量高，风险可控，成长确定性强。'),
      spacer(),

      makeTable(
        ['股票', '现价(USD)', 'P/E', '分析师12月目标', '上行%', '3年区间', '风险', '推荐指数'],
        [
          ['MSFT  微软', '$450', '27x', '~$530', '+18%', '$620–780', '⭐⭐ 低', '8.8 / 10'],
          ['GOOGL  谷歌', '$381', '30x', '~$480', '+26%', '$550–700', '⭐⭐ 低', '9.2 / 10'],
          ['AMZN  亚马逊', '$271', '32x', '~$340', '+25%', '$380–500', '⭐⭐ 低', '8.7 / 10'],
        ],
        [1700, 1200, 900, 1700, 900, 1300, 1000, 1038],
      ),
      spacer(),

      hdr('MSFT — 微软', HeadingLevel.HEADING_3),
      bullet('Azure云全球第二，AI工作负载增速最快，Copilot企业渗透加速'),
      bullet('Office 365切换成本极高，企业一旦用上就很难换掉'),
      bullet('OpenAI独家商业合作，每次AI调用都在增加微软收入'),
      bullet('从$555高位回调至$450，性价比提升'),

      spacer(),
      hdr('GOOGL — 谷歌 ⭐ 最高推荐', HeadingLevel.HEADING_3),
      bullet('搜索护城河：全球92%市场份额，60年数据积累让算法无法追赶'),
      bullet('P/E仅30x，比微软（27x）接近，但Google Cloud增速约28-30%'),
      bullet('反垄断诉讼造成恐慌折价，基本面完好 = 市场错杀的买入机会'),
      bullet('Waymo自动驾驶领先，YouTube广告，Gemini AI——多重价值被低估'),
      bullet('净现金超$1,000亿，每年回购超$600亿'),

      spacer(),
      hdr('AMZN — 亚马逊', HeadingLevel.HEADING_3),
      bullet('AWS年化收入约$1,000亿，利润率约38%，AI基础设施需求爆发'),
      bullet('广告业务$500亿+规模，年增速约20%，比Google/Meta站内精准'),
      bullet('当前P/E=32x，历史均值65x，等于用历史一半的价格买现在质量最好的亚马逊'),
      bullet('Prime会员超2亿，物流网络护城河深不可测'),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 暴涨潜力型 ──────────────────────────────────────────────────────
      hdr('2.3  暴涨潜力型', HeadingLevel.HEADING_2),
      para('核心逻辑：结构性变革早期受益者，赢家通吃市场。高风险高回报，建议控制仓位在总资金10-15%以内。'),
      spacer(),

      makeTable(
        ['股票', '现价(USD)', 'P/E', '分析师12月目标', '上行%', '3年区间（宽）', '风险', '推荐指数'],
        [
          ['NVDA  英伟达', '$224', '~45x', '$297', '+32%', '$300–500', '⭐⭐⭐⭐', '8.2 / 10'],
          ['LLY  礼来', '$1,080', '34x', '~$1,300', '+20%', '$1,400–2,200', '⭐⭐⭐', '8.0 / 10'],
          ['PLTR  Palantir', '$156', '146x', '$184', '+18%', '$100–300', '⭐⭐⭐⭐⭐', '5.5 / 10'],
        ],
        [1700, 1200, 900, 1700, 900, 1300, 1000, 1038],
      ),
      spacer(),

      hdr('NVDA — 英伟达（详见第三部分NVDA vs AMD对比）', HeadingLevel.HEADING_3),
      bullet('FY2026营收$2,159亿，毛利率85-88%，净利润率53%——真实的印钱机器'),
      bullet('AI GPU市场份额81%，CUDA生态数百万开发者，切换成本极高'),
      bullet('PEG=0.68，相对成长速度实际上比AMD更便宜'),
      bullet('风险：波动极大，AMD/定制芯片蚕食份额，DeepSeek类事件可能引发短期暴跌'),

      spacer(),
      hdr('LLY — 礼来制药', HeadingLevel.HEADING_3),
      bullet('GLP-1药物（Mounjaro/Zepbound）可能是近50年最重要的医学革命'),
      bullet('美国肥胖症患者1亿+，渗透率仍<5%，市场刚刚起步'),
      bullet('下一代口服GLP-1（orforglipron）如成功商业化，将颠覆整个市场'),
      bullet('如GLP-1被批准用于心脏病/肾病/癌症适应症，市场规模将指数级扩大'),
      bullet('风险：竞争者（诺和诺德）追赶，药物安全性问题，医保覆盖政策'),

      spacer(),
      hdr('PLTR — Palantir ⚠️ 极高风险', HeadingLevel.HEADING_3),
      bullet('P/E=146倍，极度昂贵，任何坏消息都会引发30-50%暴跌'),
      bullet('政府合同粘性高，AIP商业平台增速约55%，是真实业务'),
      bullet('建议：总资金5%以内，把它当彩票而非投资'),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 被低估型 ──────────────────────────────────────────────────────
      hdr('2.4  被低估型（市场错杀机会）', HeadingLevel.HEADING_2),
      para('核心逻辑：市场因某种短期恐惧定价过低，但基本面护城河完好，等待价值修复。'),
      spacer(),

      makeTable(
        ['股票', '现价(USD)', 'P/E', '分析师12月目标', '上行%', '3年区间', '低估原因', '推荐指数'],
        [
          ['GOOGL  谷歌', '$381', '30x', '~$480', '+26%', '$550–700', '反垄断诉讼恐慌', '9.2 / 10'],
          ['META  Meta', '$635', '24x', '$834', '+31%', '$900–1,200', 'AI能力被低估', '8.5 / 10'],
          ['JNJ  强生', '$227', '14x', '~$260', '+15%', '$280–330', '诉讼阴影折价', '7.8 / 10'],
        ],
        [1400, 1000, 800, 1500, 800, 1200, 1800, 1138],
      ),
      spacer(),

      hdr('META — Meta Platforms', HeadingLevel.HEADING_3),
      bullet('分析师共识目标价$834，比现价$635高31%，上行空间最大'),
      bullet('Llama开源AI策略：降低计算成本，吸引开发者，建立生态'),
      bullet('WhatsApp月活30亿，商业化刚刚开始，几乎被市场忽视'),
      bullet('广告AI精准度在Apple隐私限制后已超越竞争对手'),

      spacer(),
      hdr('JNJ — 强生', HeadingLevel.HEADING_3),
      bullet('P/E=14x，是11只股票中最便宜的，Dividend King（61年以上连续涨股息）'),
      bullet('滑石粉诉讼造成的折价：一旦和解，有15-20%的快速修复性上涨空间'),
      bullet('Kenvue分拆完成后，JNJ专注医疗设备+制药，业务更聚焦'),
      bullet('股息收益率约3%，等待诉讼解决期间有"等待的报酬"'),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第三部分：NVDA vs AMD
      // ══════════════════════════════════════════════════════════════════════
      hdr('三、NVDA vs AMD 深度对比', HeadingLevel.HEADING_1),
      divider(),

      para('英伟达CEO黄仁勋与AMD CEO苏姿丰是表亲，两人均出生于台湾台南。这场AI芯片战争是一对表亲之间的对决。'),
      spacer(),

      makeTable(
        ['对比维度', 'NVDA 英伟达', 'AMD 超威半导体', '谁更优'],
        [
          ['股价', '$224', '$516', '—'],
          ['FY2026年营收', '$2,159亿', '$346亿（差6倍）', '🏆 NVDA'],
          ['AI GPU市场份额', '81%', '5–7%', '🏆 NVDA'],
          ['毛利率', '85–88%', '65–68%', '🏆 NVDA'],
          ['净利润率', '约53%', '约10%', '🏆 NVDA'],
          ['市盈率 P/E(TTM)', '约45x', '169x（贵得多）', '🏆 NVDA'],
          ['远期市盈率', '约35x', '69x', '🏆 NVDA'],
          ['PEG比率', '0.68（便宜）', '1.09（偏贵）', '🏆 NVDA'],
          ['分析师12月目标', '$297（+32%）', '$472（-8.5%）', '🏆 NVDA'],
          ['CUDA/软件生态', '无可匹敌，400万+开发者', 'ROCm在追赶中', '🏆 NVDA'],
          ['数据中心收入占比', '90%（$1,937亿）', '约50%', '🏆 NVDA'],
          ['推荐指数', '8.2 / 10', '6.5 / 10', '🏆 NVDA'],
        ],
        [2800, 2400, 2400, 1038],
        C.navy,
      ),
      spacer(),

      para('⚠️  最反直觉的发现：AMD的P/E(169x)比NVDA(45x)贵得多，但基本面差很多。分析师平均目标价($472)还低于AMD现价($516)，意味着多数分析师认为AMD已被高估。'),
      spacer(),

      hdr('AMD 什么时候值得买？', HeadingLevel.HEADING_2),
      bullet('AMD跌回$380–$420区间时，P/E会降到更合理水平，届时是好买点'),
      bullet('大科技公司（Meta/Google/微软）为避免100%依赖NVDA，正在主动扶持AMD'),
      bullet('AMD MI300X在AI推理（非训练）场景性价比不错'),
      bullet('AI加速器市场2028年前从$2,000亿扩大到$5,000亿，AMD份额会从5%升至10-15%'),
      bullet('现在建议：小仓位试水（AUD$300以内），等$400以下再重仓'),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第四部分：三大IPO
      // ══════════════════════════════════════════════════════════════════════
      hdr('四、2026年三大重磅IPO分析', HeadingLevel.HEADING_1),
      divider(),

      makeTable(
        ['公司', '估值', '营收/盈利', '上市时间', '推荐指数', '建议'],
        [
          ['SpaceX', '$1.8万亿', '营收$187亿，净亏损$49亿', '2026年6月12日（本周！）', '6.0 / 10', '等3-6个月再看'],
          ['OpenAI', '$8,520亿', '未公开', '2026年秋季', '5.5 / 10', '先观察财报'],
          ['Anthropic\n(Claude母公司)', '$9,650亿', '未公开', '2026年下半年', '5.5 / 10', '先观察财报'],
        ],
        [1800, 1400, 2000, 1700, 1300, 1438],
      ),
      spacer(),

      hdr('IPO铁律：最激动人心的IPO往往最危险', HeadingLevel.HEADING_2),
      bullet('SpaceX P/S=96倍，而且2025年是净亏损——估值极度昂贵'),
      bullet('散户在IPO当天买进，机构和内部人在那天卖出——历史规律'),
      bullet('大型IPO平均开盘后3-6个月下跌15-30%（有更好的买入机会在后面）'),
      bullet('OpenAI/Anthropic盈利路径不明朗，AI模型运行成本极高'),
      bullet('建议：观望6个月，看财报数据后再决定是否买入'),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第五部分：AI泡沫分析
      // ══════════════════════════════════════════════════════════════════════
      hdr('五、AI泡沫？vs 2000年科技泡沫对比', HeadingLevel.HEADING_1),
      divider(),

      makeTable(
        ['对比维度', '2000年科技泡沫', '2026年AI'],
        [
          ['主导公司有没有收入？', '大多数没有，靠讲故事', 'NVDA年收入$2,159亿，利润率53%'],
          ['谁在主导市场？', '初创公司，无盈利历史', '微软、谷歌、亚马逊——成熟盈利巨头'],
          ['基础设施是否真实？', '97%光纤是"暗纤"，没人用', '每块GPU一出来就被预订一空'],
          ['典型估值', '宠物网站P/S=100x，无盈利', 'NVDA P/E=45x，有$2,159亿真实营收'],
          ['危险信号', '所有公司都叫".com"', 'SpaceX P/S=96x；PLTR P/E=146x'],
          ['市场集中度', '部分集中', '前5大公司占S&P500的30%，历史最高'],
        ],
        [2400, 3200, 4038],
      ),
      spacer(),

      hdr('结论：部分是，部分不是', HeadingLevel.HEADING_2),
      bullet('✅ 不是泡沫：NVDA/MSFT/GOOGL有真实AI收入和利润，GPU需求100%真实'),
      bullet('⚠️ 有泡沫成分：SpaceX P/S=96x，PLTR P/E=146x，OpenAI估值$8,520亿无盈利支撑'),
      bullet('整体判断：基础设施层（NVDA/MSFT/GOOGL）是真实的；应用/故事层有泡沫'),
      bullet('AI基础设施链中，存储和光通讯是相对被低估的环节'),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第六部分：AI基础设施铲子股
      // ══════════════════════════════════════════════════════════════════════
      hdr('六、AI基础设施"铲子股"', HeadingLevel.HEADING_1),
      divider(),

      para('淘金热时最赚钱的不是淘金者，而是卖铲子的人。AI时代：NVDA是金，存储和光通讯是铲子。'),
      spacer(),

      hdr('存储类', HeadingLevel.HEADING_2),
      makeTable(
        ['公司', '代码', '现价', '为什么重要', '推荐指数'],
        [
          ['美光科技', 'MU', '$1,041', 'AI芯片需要HBM高带宽内存，MU是主要供应商；2026年已暴涨304%', '7.5/10 等回调'],
          ['希捷', 'STX', '待查', 'AI训练数据需要大容量硬盘，Q2财报超预期目标价上调50%', '7.5/10'],
          ['Pure Storage', 'PSTG', '待查', '企业级全闪存，AI推理专用', '7.0/10'],
        ],
        [1400, 900, 900, 4000, 1438],
      ),
      spacer(),

      hdr('光通讯类', HeadingLevel.HEADING_2),
      para('AI数据中心内部和数据中心之间需要传输海量数据，铜线不够快，光纤成为必须。'),
      para('关键数据：800G以上光收发器出货量从2025年的2,400万个→2026年的6,300万个，增长163%！'),
      spacer(),

      makeTable(
        ['公司', '代码', '现价', '为什么重要', '推荐指数'],
        [
          ['Ciena', 'CIEN', '$570', 'AI数据中心光网络整体解决方案，Q2 EPS同比增247%！', '8.0/10'],
          ['Coherent', 'COHR', '待查', '光收发器/激光器，AI数据中心内部连接核心', '7.5/10'],
          ['Lumentum', 'LITE', '待查', '激光器+光收发器，2026年Q2是重大拐点', '7.0/10'],
          ['Credo Tech', 'CRDO', '待查', '高速以太网连接芯片，小公司但增速极快', '7.0/10'],
        ],
        [1400, 900, 900, 4000, 1438],
      ),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第七部分：AUD$6,000投资策略
      // ══════════════════════════════════════════════════════════════════════
      hdr('七、AUD$6,000 三次买入完整策略', HeadingLevel.HEADING_1),
      divider(),

      mixed(bold('汇率：'), normal('AUD $1 = USD $0.716（2026年6月）')),
      mixed(bold('总金额：'), normal('AUD $6,000 ≈ USD $4,297')),
      mixed(bold('分三次：'), normal('每次 AUD $2,000 ≈ USD $1,432')),
      spacer(),

      hdr('第一次买入 — 今天（AUD $2,000）', HeadingLevel.HEADING_2),
      para('策略：买最有把握的核心底仓，即使市场明天大跌也能睡得着觉。'),
      spacer(),

      makeTable(
        ['股票', '买入金额(AUD)', '约美元', '约股数', '买入理由'],
        [
          ['GOOGL  谷歌', '$900', '~$644', '约1.7股', '9.2分最高推荐，最被低估的高质量AI公司'],
          ['MSFT  微软', '$700', '~$501', '约1.1股', '8.8分，从高位回调，AI最确定受益者'],
          ['NVDA  英伟达', '$400', '~$286', '约1.3股', '8.2分，PEG=0.68比AMD更便宜，AI芯片王者'],
        ],
        [1600, 1600, 1200, 1200, 4038],
      ),
      spacer(),

      hdr('第二次买入 — 1个月后（AUD $2,000）', HeadingLevel.HEADING_2),
      para('策略：加入高上行潜力股 + AI基础设施铲子 + 小仓位试水AMD。等待SpaceX IPO情绪退烧后的回调机会。'),
      spacer(),

      makeTable(
        ['股票', '买入金额(AUD)', '约美元', '约股数', '买入理由'],
        [
          ['META  Meta', '$700', '~$501', '约0.8股', '8.5分，分析师目标上行31%，WhatsApp价值未被计入'],
          ['AMZN  亚马逊', '$600', '~$430', '约1.6股', '8.7分，P/E是历史均值一半，AWS利润飞轮'],
          ['CIEN  光通讯', '$400', '~$287', '约0.5股', '8.0分，AI铲子股，EPS同比增247%'],
          ['AMD  超威半导体', '$300', '~$215', '约0.4股', '6.5分，小仓位试水，等$400以下再重仓'],
        ],
        [1600, 1600, 1200, 1200, 4038],
      ),
      spacer(),

      hdr('第三次买入 — 3个月后（AUD $2,000）', HeadingLevel.HEADING_2),
      para('策略：根据市场情况灵活调整。'),
      spacer(),

      makeTable(
        ['情况', '操作', '原因'],
        [
          ['GOOGL/MSFT跌了', '加仓它们', '好公司跌价=打折，这是礼物不是坏事'],
          ['AMD跌到$400以下', '大力加仓AMD', '那才是合理估值，好时机'],
          ['NVDA跌到$180以下', '加仓NVDA', 'PEG更低，AI需求没变'],
          ['市场整体下跌', '继续按计划买', '分批买入摊低成本，不要慌'],
          ['所有股票都涨了', '考虑加MU或BRK.B', 'MU如果从高位回调是好机会'],
        ],
        [2200, 2800, 4638],
      ),
      spacer(),

      hdr('最终组合概览', HeadingLevel.HEADING_2),
      makeTable(
        ['类别', '股票', '总计划金额(AUD)', '占比'],
        [
          ['核心底仓（最稳）', 'GOOGL + MSFT + NVDA', '$2,000', '33%'],
          ['成长潜力', 'META + AMZN', '$1,300', '22%'],
          ['AI芯片竞争者', 'AMD', '$800（分2-3次）', '13%'],
          ['基础设施铲子', 'CIEN', '$400', '7%'],
          ['灵活备用', '视情况加仓', '$1,500', '25%'],
          ['合计', '', '$6,000', '100%'],
        ],
        [2200, 2200, 2200, 3038],
      ),

      new Paragraph({ children: [new PageBreak()] }),

      // ══════════════════════════════════════════════════════════════════════
      //  第八部分：全景推荐排行榜
      // ══════════════════════════════════════════════════════════════════════
      hdr('八、全景推荐排行榜', HeadingLevel.HEADING_1),
      divider(),

      makeTable(
        ['排名', '股票', '现价(USD)', 'P/E', '推荐指数', '核心理由'],
        [
          ['🥇 1', 'GOOGL  谷歌', '$381', '30x', '9.2 / 10', '最低估的高质量AI公司，反垄断折价是机会'],
          ['🥈 2', 'V  Visa', '$327', '30x', '8.8 / 10', '最强网络效应护城河，全球现金电子化趋势'],
          ['🥈 2', 'MSFT  微软', '$450', '27x', '8.8 / 10', '最确定的AI受益者，Copilot渗透提速'],
          ['4', 'AMZN  亚马逊', '$271', '32x', '8.7 / 10', '历史低P/E，AWS+广告双飞轮'],
          ['5', 'META  Meta', '$635', '24x', '8.5 / 10', '分析师最大上行空间31%'],
          ['5', 'BRK.B  巴菲特', '$473', '17x', '8.5 / 10', '最安全底仓，$3,000亿现金护体'],
          ['7', 'NVDA  英伟达', '$224', '~45x', '8.2 / 10', 'AI芯片王者，PEG=0.68比AMD便宜'],
          ['8', 'LLY  礼来', '$1,080', '34x', '8.0 / 10', 'GLP-1医学革命早期阶段'],
          ['8', 'PG  宝洁', '$147', '22x', '8.0 / 10', '最稳股息，消费品护城河'],
          ['10', 'JNJ  强生', '$227', '14x', '7.8 / 10', '最便宜P/E，诉讼折价一旦解决大幅修复'],
          ['11', 'AMD  超威半导体', '$516', '169x', '6.5 / 10', '好公司但现价太贵，等$400以下'],
          ['12', 'PLTR  Palantir', '$156', '146x', '5.5 / 10', 'P/E 146x极贵，最多用5%资金当彩票'],
        ],
        [600, 1600, 1200, 800, 1200, 4238],
      ),

      spacer(),
      divider(),
      spacer(),

      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 200, after: 100 },
        children: [new TextRun({ text: '重要提醒', font: 'Arial', size: 28, bold: true, color: C.navy })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 60, after: 60 },
        children: [new TextRun({
          text: '不要把所有积蓄都投入股市。这AUD$6,000应是能放3-5年不动的闲钱。',
          font: 'Arial', size: 22, color: '333333',
        })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 60, after: 60 },
        children: [new TextRun({
          text: '分三次买入（不要一次性全买），让时间帮你平摊成本。',
          font: 'Arial', size: 22, color: '333333',
        })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 60, after: 200 },
        children: [new TextRun({
          text: '好公司跌了不要慌，那是打折买入的机会，不是卖出信号。',
          font: 'Arial', size: 22, bold: true, color: C.navy,
        })],
      }),

    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('美股投资分析报告.docx', buffer);
  console.log('✅ 文档生成成功：美股投资分析报告.docx');
}).catch(err => {
  console.error('❌ 生成失败：', err);
});
