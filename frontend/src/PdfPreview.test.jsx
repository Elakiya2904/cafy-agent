import { describe, it, expect, vi, beforeEach } from 'vitest';

// Fake renderer: a "PDF" records the step it was rendered at, and fits on one page only at or
// below `fitsAt` points. This lets the tests count renders without drawing real PDFs.
let fitsAt = 10;
const renders = [];
vi.mock('@react-pdf/renderer', async (importOriginal) => ({
  ...(await importOriginal()),
  pdf: (element) => ({
    toBlob: async () => {
      const { fontSize, density } = element.props.settings;
      renders.push(`${fontSize}/${density}`);
      return { fontSize, density };
    },
  }),
}));
vi.mock('./pdfUtils.js', () => ({
  countPdfPages: async (blob) => (blob.fontSize <= fitsAt ? 1 : 2),
}));

const { fitSteps, renderFitted } = await import('./PdfPreview.jsx');

const settings = { font: 'Helvetica', fontSize: 10, density: 'normal', accent: '#000', autoFit: true };
const resume = (text) => ({ professional_summary: text });

beforeEach(() => { renders.length = 0; });

describe('PDF auto-fit', () => {
  it('steps down in half points to 9.5 pt (still readable), then tries compact spacing', () => {
    expect(fitSteps(settings).map((s) => `${s.size}/${s.density}`)).toEqual([
      '10/normal', '9.5/normal', '9.5/compact',
    ]);
  });

  it('renders once when nothing needs fitting', async () => {
    fitsAt = 10;
    const result = await renderFitted(resume('short'), settings, {});
    expect(result.size).toBe(10);
    expect(renders).toEqual(['10/normal']);
  });

  it('resumes from the last fitted size instead of starting from the top', async () => {
    fitsAt = 9.5;
    const memo = {};
    expect((await renderFitted(resume('long text'), settings, memo)).size).toBe(9.5);
    expect(renders).toHaveLength(2);

    // The text grew but still fits at 9.5 pt: a single render.
    renders.length = 0;
    expect((await renderFitted(resume('long text, longer'), settings, memo)).size).toBe(9.5);
    expect(renders).toEqual(['9.5/normal']);

    // The text got shorter and now fits at 10 pt: it climbs back up.
    fitsAt = 10;
    renders.length = 0;
    expect((await renderFitted(resume('short'), settings, memo)).size).toBe(10);
    expect(renders).toEqual(['9.5/normal', '10/normal']);
  });

  it('stops a stale search as soon as a newer edit arrives', async () => {
    fitsAt = 8;
    await expect(renderFitted(resume('x'), settings, {}, () => renders.length >= 1)).rejects.toThrow();
    expect(renders).toEqual(['10/normal']);
  });
});
