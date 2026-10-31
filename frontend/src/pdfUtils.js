// pdfkit (used by @react-pdf/renderer) writes the page tree uncompressed, so the page count can be
// read straight from the bytes without bundling a PDF parser.
export function countPdfPagesFromBytes(bytes) {
  let text = "";
  for (let i = 0; i < bytes.length; i += 8192) {
    text += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
  }
  const tree = text.match(/\/Type\s*\/Pages[\s\S]{0,200}?\/Count\s+(\d+)/) || text.match(/\/Count\s+(\d+)[\s\S]{0,200}?\/Type\s*\/Pages/);
  if (tree) return Number(tree[1]);
  const leaves = text.match(/\/Type\s*\/Page(?![s\w])/g);
  return leaves ? leaves.length : 1;
}

export async function countPdfPages(blob) {
  const buffer = await new Response(blob).arrayBuffer();
  return countPdfPagesFromBytes(new Uint8Array(buffer));
}
