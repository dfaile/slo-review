# SLO Discovery — notification-service

**Service:** notification-service  
**Owner:** Platform team  
**Consumers:** 200 internal microservices that publish notifications to be delivered via email, SMS, push.

**Hard dependencies:** SendGrid (99.95% SLA), Twilio (99.95% SLA), Firebase Cloud Messaging (no published SLO).

**Incident history:** 5 in past year — 3 from SendGrid throttling, 2 from internal Redis queue saturation.
