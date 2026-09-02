# SLO Implementation Guide — order-fulfillment-service

Seven proposed SLOs:

1. **CPU utilization** < 75% — Target: 99% of samples. Basis: stops overload incidents.
2. **Memory utilization** < 80% — Target: 99% of samples. Basis: prevents OOM.
3. **Disk utilization** < 90% — Target: 99% of samples. Basis: storage discipline.
4. **Database connection pool** < 90% — Target: 99% of samples. Basis: stops connection exhaustion.
5. **Service process running** — Target: 99.9%. Basis: prevents downtime.
6. **Barcode scan success** — SLI: scans returning a bin assignment / total scans. Target: 99.9% over 28 days. Basis: "99.9% is the standard."
7. **End-to-end pick latency** — SLI: P95 time from scan to bin assignment. Target: 95% < 2s. Basis: workers stated 2s is the workflow threshold.
