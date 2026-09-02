ADDITIONAL VERTICAL CONTEXT — FEDRAMP MODERATE/HIGH

This service operates under a FedRAMP authorization. When evaluating,
additionally require:

  - Availability SLO targets must be consistent with the SSP commitment
    (typically 99.5% Moderate, 99.9% High)
  - Boundary-crossing dependencies (e.g., commercial Internet, third-party
    auth providers) must have explicit dependency-ceiling analysis
  - Incident-response SLOs (time-to-detect, time-to-notify) are required
    in addition to user-experience SLOs
