ADDITIONAL VERTICAL CONTEXT — PCI-DSS / FINANCIAL SERVICES

This service handles or supports cardholder data flows. When evaluating,
additionally require:

  - Transaction success rate SLO present (not just availability)
  - Latency SLOs for any user-facing payment flow (P95 < 3s typical)
  - Fraud-detection latency SLO present if the service includes risk
    decisioning
  - Reconciliation SLO (settlement match rate) present for clearing
    systems
