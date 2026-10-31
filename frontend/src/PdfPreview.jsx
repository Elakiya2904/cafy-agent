import React, { useEffect, useRef, useState } from "react";
import { pdf } from "@react-pdf/renderer";
import ResumePdf from "./ResumePdf.jsx";
import { countPdfPages } from "./pdfUtils.js";

const RENDER_DEBOUNCE_MS = 450;

// Renders the resume, and when auto-fit is on, steps the font size (then spacing) down until it
// fits on one page. Returns the PDF plus what was actually used.
async function renderFitted(resume, settings) {
  let size = settings.fontSize;
  let density = settings.density;
  for (;;) {
    const blob = await pdf(<ResumePdf resume={resume} settings={{ ...settings, fontSize: size, density }} />).toBlob();
    const pages = await countPdfPages(blob);
    if (pages <= 1 || !settings.autoFit) return { blob, pages, size, density };
    if (size > 8.5) size = Math.round((size - 0.5) * 10) / 10;
    else if (density !== "compact") density = "compact";
    else return { blob, pages, size, density };
  }
}

export default function PdfPreview({ resume, settings, onRendered }) {
  // Two stacked frames: the new PDF loads invisibly and swaps in, so typing never flashes white.
  const [shown, setShown] = useState(null);
  const [pending, setPending] = useState(null);
  const urls = useRef(new Set());
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await renderFitted(resume, settings);
        if (cancelled) return;
        const url = URL.createObjectURL(result.blob);
        urls.current.add(url);
        setError(null);
        setPending(url);
        onRendered(result);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }, RENDER_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [resume, settings, onRendered]);

  useEffect(() => () => urls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  // Throwing hands off to the error boundary, which shows the HTML preview instead.
  if (error) throw error;

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
