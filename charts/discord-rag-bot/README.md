Helm Chart: discord-rag-bot

This chart deploys the Discord RAG bot and multiple queue workers (ingest, checksum, prune) as separate Deployments.

Quick start

- Install with minimal required secrets and env:

  helm install my-rag charts/discord-rag-bot \
    --set global.secretEnv.APP_DISCORD_TOKEN="<discord-token>" \
    --set global.secretEnv.APP_PG_PASSWORD="postgres" \
    --set global.secretEnv.OPENAI_API_KEY="" \
    --set global.secretEnv.APP_RABBITMQ_URL="amqp://user:pass@rabbitmq:5672/" \
    --set global.env.APP_PG_HOST="postgres" \
    --set global.env.APP_PG_PORT="5432" \
    --set global.env.APP_PG_USER="postgres" \
    --set global.env.APP_PG_DATABASE="postgres"

- Configure queues (optional). Defaults to one queue `rag_jobs` for all types:

  values.yaml
    global:
      jobQueues:
        default: rag_jobs
        ingest: rag_ingest
        checksum: rag_checksum
        prune: rag_prune

Workers per queue

- Deploy one worker Deployment per type in `workers.types`.
- Each worker sets `APP_WORKER_QUEUE_TYPE` accordingly and consumes jobs from the matching queue name.

Notable values

- image.repository/tag: container image for both bot and workers
- global.env / global.secretEnv: environment variables for ConfigMap/Secret
- global.jobBackend: postgres or rabbitmq (default rabbitmq)
- global.jobQueues.*: queue names per job type
- bot.*: bot Deployment/Service/HPA settings
- workers.*: worker Deployments and autoscaling settings

