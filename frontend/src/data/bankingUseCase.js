export const bankingUseCase = {
  fileSlug: "vaaksetu-banking-use-case",
  verticalLabel: "Collections and Recovery Automation",
  title: "Loan & Debt Automation",
  subtitle:
    "VaakSetu turns multilingual repayment calls into structured collections intelligence with customer intent, payment timelines, and compliance-ready records.",
  executiveSummary:
    "This demo represents an outbound collections interaction where the assistant confirms repayment status, records the promised date, and captures the customer's reason for delay. The result can feed dashboards, follow-up queues, and audit workflows automatically.",
  transcript: [
    {
      label: "Assistant",
      role: "assistant",
      text: "Hello, I am calling about your pending EMI. Could you confirm whether payment can be completed this week?",
      meta: "Outbound collections opener",
    },
    {
      label: "Customer",
      role: "customer",
      text: "Salary is delayed. I can pay by Friday evening.",
      meta: "Payment commitment",
    },
    {
      label: "Assistant",
      role: "assistant",
      text: "Understood. I have recorded Friday evening as the promised repayment time.",
      meta: "Commitment logged",
    },
  ],
  structuredTitle: "Structured collections output",
  structuredRows: [
    { label: "Payment Status", value: "Promise to pay" },
    { label: "Promised Date", value: "Friday evening" },
    { label: "Reason for Delay", value: "Salary delayed" },
    { label: "Confidence", value: "High" },
    { label: "Next Action", value: "Follow-up reminder on due date" },
  ],
  compliance: {
    title: "Compliance notes",
    bullets: [
      "Every repayment conversation can be logged with a timestamped summary and customer commitment.",
      "Structured outputs reduce ambiguity in follow-up handling and help create cleaner audit trails.",
    ],
  },
};
