// Renders a use-case object from src/data/* into a downloadable PDF.
async function downloadUseCasePdf(useCase) {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 48;
  const contentWidth = doc.internal.pageSize.getWidth() - margin * 2;
  let y = margin;

  const ensureSpace = (needed) => {
    if (y + needed > pageHeight - margin) {
      doc.addPage();
      y = margin;
    }
  };

  const addText = (text, { size = 10, bold = false, gap = 4 } = {}) => {
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(String(text), contentWidth);
    ensureSpace(lines.length * (size + 4) + gap);
    doc.text(lines, margin, y);
    y += lines.length * (size + 4) + gap;
  };

  const addSection = (title) => {
    y += 8;
    addText(title, { size: 13, bold: true });
  };

  addText(useCase.title, { size: 20, bold: true, gap: 6 });
  addText(useCase.verticalLabel, { size: 11, bold: true });
  addText(useCase.subtitle);

  addSection("Executive summary");
  addText(useCase.executiveSummary);

  addSection("Sample conversation");
  for (const turn of useCase.transcript || []) {
    addText(`${turn.label}: ${turn.text}`);
  }

  addSection(useCase.structuredTitle || "Structured output");
  for (const row of useCase.structuredRows || []) {
    addText(`- ${row.label}: ${row.value}`);
  }

  if (useCase.highlight) {
    addSection(useCase.highlight.title);
    addText(useCase.highlight.body);
  }
  if (useCase.features?.length) {
    addSection("Capabilities");
    for (const f of useCase.features) addText(`- ${f.title}: ${f.desc}`);
  }
  if (useCase.compliance) {
    addSection(useCase.compliance.title);
    for (const b of useCase.compliance.bullets || []) addText(`- ${b}`);
  }

  doc.save(`${useCase.fileSlug || "vaaksetu-use-case"}.pdf`);
}

export const downloadBankingUseCasePdf = downloadUseCasePdf;
export const downloadHealthcareUseCasePdf = downloadUseCasePdf;
