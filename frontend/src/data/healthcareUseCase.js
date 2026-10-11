export const healthcareUseCase = {
  fileSlug: "vaaksetu-healthcare-use-case",
  verticalLabel: "Healthcare Emergency Workflow",
  title: "Healthcare & Emergency AI",
  subtitle:
    "VaakSetu helps field workers and emergency teams capture symptoms, risk signals, and follow-up actions from multilingual voice conversations in real time.",
  executiveSummary:
    "This demo shows a patient triage flow where the assistant captures symptoms, duration, medication status, and risk level from a short multilingual exchange. The output is structured immediately so clinical teams can review the case without replaying the full call.",
  transcript: [
    {
      label: "Patient",
      role: "patient",
      text: "I have had fever for three days and I am not taking any medication right now.",
      meta: "English, initial complaint",
    },
    {
      label: "Assistant",
      role: "assistant",
      text: "Okay, three days of fever and no medication. Have you had fevers like this before, or is this new for you?",
      meta: "Clarifying history",
    },
    {
      label: "Patient",
      role: "patient",
      text: "This is the first time. I also feel weak and cold at night.",
      meta: "Additional symptoms",
    },
  ],
  structuredTitle: "Structured triage record",
  structuredRows: [
    { label: "Symptoms", value: "Fever, weakness, chills at night" },
    { label: "Duration", value: "Three days" },
    { label: "Medication Status", value: "No current medication" },
    { label: "History", value: "First episode reported" },
    { label: "Risk Level", value: "Moderate - monitor and follow up" },
  ],
  highlight: {
    title: "Operational impact",
    body:
      "The same conversation becomes a clean triage summary that can be routed to a clinician, supervisor, or escalation desk without manual note-taking.",
  },
  features: [
    {
      title: "Code-mixed capture",
      desc: "Handles real-world multilingual patient speech instead of requiring rigid scripted responses.",
    },
    {
      title: "Structured extraction",
      desc: "Auto-fills the symptom timeline, medication status, and follow-up context in one pass.",
    },
    {
      title: "Faster escalation",
      desc: "Critical cases can be flagged quickly with a usable summary ready for human review.",
    },
  ],
};
