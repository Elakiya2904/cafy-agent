/**
 * Render and preview a resume PDF in the browser.
 * Manages asynchronous document rendering, zoom, and preview error states.
 */
import React, { useEffect, useRef, useState } from "react";
import { pdf } from "@react-pdf/renderer";
import ResumePdf from "./ResumePdf.jsx";
import { countPdfPages } from "./pdfUtils.js";

const RENDER_DEBOUNCE_MS = 350;
const MIN_FONT_SIZE = 8.5;

// Auto-fit tries these (font size, spacing) steps in order: the chosen size, smaller sizes in
// half-point steps down to 8.5 pt, then compact spacing at the smallest size.
export function fitSteps(settings) {
  const steps = [];
  let size = settings.fontSize;
  steps.push({ size, density: settings.density });
  while (size > MIN_FONT_SIZE) {
    size = Math.round((size - 0.5) * 10) / 10;
    steps.push({ size, density: settings.density });
  }
  if (settings.density !== "compact") steps.push({ size, density: "compact" });
  return steps;
}

async function renderStep(resume, settings, step) {
  const blob = await pdf(<ResumePdf resume={resume} settings={{ ...settings, fontSize: step.size, density: step.density }} />).toBlob();
  return { blob, pages: await countPdfPages(blob), size: step.size, density: step.density };
}

class Cancelled extends Error {}

// Finds the largest step that fits on one page. Each render takes a noticeable fraction of a
// second, so the search starts from the step that fitted last time instead of the top:
//  - it still fits and the text did not get shorter: one render, done;
//  - it still fits and the text got shorter: also try larger steps;
//  - it no longer fits: try smaller steps.
// `memo` carries the last step index and text length between calls.
export async function renderFitted(resume, settings, memo = {}, isCancelled = () => false) {
  const steps = fitSteps(settings);
  if (!settings.autoFit) return renderStep(resume, settings, steps[0]);

  const key = `${settings.font}|${settings.fontSize}|${settings.density}`;
  const length = JSON.stringify(resume || {}).length;
  const start = memo.key === key ? Math.min(memo.index ?? 0, steps.length - 1) : 0;
  const shrank = memo.key === key && length < (memo.length ?? 0);
  const check = () => { if (isCancelled()) throw new Cancelled(); };

  let i = start;
  let result = await renderStep(resume, settings, steps[i]);
  if (result.pages <= 1) {
    while (shrank && i > 0) {
      check();
      const bigger = await renderStep(resume, settings, steps[i - 1]);
      if (bigger.pages > 1) break;
      i -= 1;
      result = bigger;
    }
  } else {
    while (i < steps.length - 1) {
      check();
      i += 1;
      result = await renderStep(resume, settings, steps[i]);
      if (result.pages <= 1) break;
    }
  }
  Object.assign(memo, { key, index: i, length });
  return result;
}

export default function PdfPreview({ resume, settings, onRendered }) {
  // Two stacked frames: the new PDF loads invisibly and swaps in, so typing never flashes white.
  const [shown, setShown] = useState(null);
  const [pending, setPending] = useState(null);
  const urls = useRef(new Set());
  const memo = useRef({});
  const lastInput = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Undo/redo or an edit that was reverted can produce identical content: nothing to redraw.
    const input = JSON.stringify([resume, settings]);
    if (input === lastInput.current) return undefined;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await renderFitted(resume, settings, memo.current, () => cancelled);
        if (cancelled) return;
        lastInput.current = input;
        const url = URL.createObjectURL(result.blob);
        urls.current.add(url);
        setError(null);
        setPending(url);
        onRendered(result);
      } catch (e) {
        if (!cancelled && !(e instanceof Cancelled)) setError(e);
      }
    }, lastInput.current === null ? 0 : RENDER_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [resume, settings, onRendered]);

  useEffect(() => () => urls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  const swap = (url) => {
    setShown(url);
    setPending((p) => (p === url ? null : p));
    urls.current.forEach((u) => {
      if (u !== url) {
        URL.revokeObjectURL(u);
        urls.current.delete(u);
      }
    });
  };
  const src = (u) => `${u}#toolbar=0&navpanes=0&view=FitH`;

  if (error) {
    return (
      <div className="re-preview-error" role="alert">
        <strong>Could not render the PDF preview.</strong>
        <span>{error.message || "An unexpected PDF rendering error occurred."}</span>
      </div>
    );
  }

  return (
    <div className="re-pdf">
      {shown && <iframe key={shown} title="Resume PDF preview" src={src(shown)} className="re-pdf-frame" />}
      {pending && pending !== shown && (
        <iframe key={pending} title="Resume PDF preview (updating)" src={src(pending)} className="re-pdf-frame re-pdf-next" onLoad={() => swap(pending)} aria-hidden="true" />
      )}
      {!shown && !pending && <div className="re-loading">Rendering preview…</div>}
    </div>
  );
}
