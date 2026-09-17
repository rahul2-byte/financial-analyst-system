# Deployment levels

| Level | Runtime | Storage | Gate |
| --- | --- | --- | --- |
| Local research | one CLI process | `.finai` filesystem | offline evaluation + smoke test |
| Shared research | one service process | shared object storage/Postgres | measured concurrency and retention need |
| Production decision support | redundant services | managed durable stores | SLOs, RBAC, audit and replay evidence |

Kafka, Kubernetes, vector databases, and HFT execution are intentionally deferred;
the current single-user workload does not justify their operational cost.
