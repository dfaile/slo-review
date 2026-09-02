# SLO Implementation Guide — notification-service

Four proposed SLOs:

1. **Email delivery success** — SLI: SendGrid delivered/total emails. Target: 99.5% over 28 days. Basis: matches SendGrid SLA floor.
2. **SMS delivery success** — SLI: Twilio delivered/total SMS. Target: 99.5% over 28 days. Basis: matches Twilio SLA floor.
3. **Push delivery success** — SLI: FCM ack rate. Target: 99.9% over 28 days. Basis: 99.9% is industry standard for push.
4. **Redis queue health** — SLI: Redis memory usage < 80%. Target: 99% of samples over 28 days. Basis: prevents the 2 outages we had last year.
