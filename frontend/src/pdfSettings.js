// Shared PDF layout defaults for font, margins, and page configuration.
// Kept separate so the editor can read settings without loading the PDF renderer.
// ResumePdf and the editor use these values to keep preview/export settings aligned.
export const DEFAULT_PDF_SETTINGS = {
  font: "Helvetica",
  fontSize: 10,
  accent: "#1e293b",
  density: "normal",
  autoFit: true,
};

export const PDF_FONTS = ["Helvetica", "Times-Roman", "Courier"];
export const PDF_ACCENTS = ["#1e293b", "#1d4ed8", "#0f766e", "#7c3aed", "#be123c"];

export function loadPdfSettings() {
  try {
    const saved = typeof localStorage === "undefined"
      ? null
      : JSON.parse(localStorage.getItem("cafy.resumePdfSettings") || "null");
    return saved && typeof saved === "object"
      ? { ...DEFAULT_PDF_SETTINGS, ...saved }
      : DEFAULT_PDF_SETTINGS;
  } catch {
    return DEFAULT_PDF_SETTINGS;
  }
}
