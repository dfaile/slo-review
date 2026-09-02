# SLO Discovery — order-fulfillment-service

**Consumers:** warehouse staff at 12 distribution centers.

**Critical user journey:** scan barcode → system assigns bin → worker picks → system confirms.

**Hard dependencies:** WMS-DB (PostgreSQL, no documented SLO), internal auth (99.9%), barcode scanner gateway.

**Incident history:** 14 incidents in past 6 months, mostly during peak shifts.
