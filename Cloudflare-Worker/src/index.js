const GITHUB_OWNER = 'BHG-App-Studios';
const GITHUB_REPOSITORY = 'Palki-Sahib-Video-Creator-Test';
const GITHUB_WORKFLOW = 'gurbani-ai.yml';
const GITHUB_REF = 'main';
const COMPLETION_TTL_SECONDS = 12 * 60 * 60;
const ACTIVE_RUN_STATUSES = [
    'queued',
    'in_progress',
    'requested',
    'waiting',
    'pending',
];

function githubHeaders(env) {
    return {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'palki-sahib-video-creator-trigger',
    };
}

function currentIstDate() {
    const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
}

function completionKey(date) {
    return `gurbani-ai:completed:${date}`;
}

async function hasCompletedToday(env) {
    if (!env.RUN_STATUS_KV) {
        throw new Error('RUN_STATUS_KV KV binding is missing.');
    }
    return (await env.RUN_STATUS_KV.get(completionKey(currentIstDate()))) !== null;
}

async function hasActiveWorkflowRun(env) {
    const responses = await Promise.all(
        ACTIVE_RUN_STATUSES.map((status) => fetch(
            `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPOSITORY}/actions/runs?status=${status}&per_page=100`,
            { headers: githubHeaders(env) }
        ))
    );

    for (const response of responses) {
        if (!response.ok) {
            throw new Error(
                `GitHub active-run check failed (${response.status}): ${await response.text()}`
            );
        }
        if ((await response.json()).total_count > 0) {
            return true;
        }
    }
    return false;
}

async function triggerGitHubWorkflow(env) {
    if (!env.GITHUB_ACTIONS_TOKEN) {
        throw new Error('GITHUB_ACTIONS_TOKEN Worker secret is missing.');
    }
    if (await hasCompletedToday(env)) {
        console.log('Today already completed successfully. Skipping dispatch.');
        return { triggered: false, reason: 'completed_today' };
    }
    if (await hasActiveWorkflowRun(env)) {
        console.log('An existing GitHub Actions run is active. Skipping dispatch.');
        return { triggered: false, reason: 'active_run' };
    }

    const response = await fetch(
        `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPOSITORY}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`,
        {
            method: 'POST',
            headers: { ...githubHeaders(env), 'Content-Type': 'application/json' },
            body: JSON.stringify({ ref: GITHUB_REF }),
        }
    );
    if (!response.ok) {
        throw new Error(
            `GitHub workflow dispatch failed (${response.status}): ${await response.text()}`
        );
    }
    console.log('Triggered gurbani-ai.yml successfully.');
    return { triggered: true, reason: 'dispatched' };
}

function authorized(request, secret) {
    return Boolean(secret) && request.headers.get('Authorization') === `Bearer ${secret}`;
}

async function markCompletion(request, env) {
    if (!authorized(request, env.RUN_COMPLETION_SECRET)) {
        return Response.json({ error: 'Unauthorized.' }, { status: 401 });
    }
    if (!env.RUN_STATUS_KV) {
        return Response.json({ error: 'RUN_STATUS_KV KV binding is missing.' }, { status: 500 });
    }

    let payload;
    try {
        payload = await request.json();
    } catch {
        return Response.json({ error: 'Request body must be valid JSON.' }, { status: 400 });
    }

    const today = currentIstDate();
    if (payload.status !== 'success' || payload.date !== today) {
        return Response.json(
            { error: 'Only a successful completion for today IST can be recorded.', today },
            { status: 400 }
        );
    }

    await env.RUN_STATUS_KV.put(
        completionKey(today),
        JSON.stringify({ date: today, status: 'success', completedAt: new Date().toISOString() }),
        { expirationTtl: COMPLETION_TTL_SECONDS }
    );
    console.log(`Recorded successful completion for ${today}.`);
    return Response.json({ recorded: true, date: today }, { status: 201 });
}

async function checkRunStatus(request, env) {
    if (!authorized(request, env.RUN_COMPLETION_SECRET)) {
        return Response.json({ error: 'Unauthorized.' }, { status: 401 });
    }
    const date = currentIstDate();
    const completed = await hasCompletedToday(env);
    return Response.json({ date, completed }, { status: 200 });
}

export default {
    async scheduled(controller, env, ctx) {
        ctx.waitUntil(triggerGitHubWorkflow(env).catch((error) => {
            console.error(`Could not trigger GitHub Actions: ${error.message}`);
            controller.noRetry();
        }));
    },

    async fetch(request, env) {
        const url = new URL(request.url);
        if (request.method === 'GET' && url.pathname === '/') {
            return new Response('Palki Sahib GitHub trigger is active.', { status: 200 });
        }
        if (request.method === 'POST' && url.pathname === '/trigger') {
            if (!authorized(request, env.MANUAL_TRIGGER_SECRET)) {
                return Response.json({ error: 'Unauthorized.' }, { status: 401 });
            }
            try {
                const result = await triggerGitHubWorkflow(env);
                return Response.json(result, { status: result.triggered ? 202 : 200 });
            } catch (error) {
                return Response.json({ error: error.message }, { status: 502 });
            }
        }
        if (request.method === 'POST' && url.pathname === '/complete') {
            return markCompletion(request, env);
        }
        if (request.method === 'POST' && url.pathname === '/checkRunStatus') {
            try {
                return await checkRunStatus(request, env);
            } catch (error) {
                return Response.json({ error: error.message }, { status: 502 });
            }
        }
        return new Response('Not found', { status: 404 });
    },
};
