# Palki Sahib GitHub Trigger Worker

The Worker checks today's IST completion key and active GitHub Actions runs
before dispatching `gurbani-ai.yml`. A successful publisher run calls
`POST /complete`, which stores the date in KV for 12 hours. Failed runs never
call that endpoint, so a later Cron Trigger can retry the day.

Before publishing, the runner calls the authenticated `POST /checkRunStatus`
endpoint once. A completed day skips publishing; an incomplete day continues.

Required Worker secrets:

```text
GITHUB_ACTIONS_TOKEN
MANUAL_TRIGGER_SECRET
RUN_COMPLETION_SECRET
```

Required KV binding: `RUN_STATUS_KV`.

The GitHub workflow also needs the secret `RUN_COMPLETION_SECRET`, passed to
the job as an environment variable. Deploy the Worker after creating the KV
namespace and replacing the placeholder namespace ID in `wrangler.toml`.
