const crypto = require('crypto');

const projectId = process.env.FIREBASE_PROJECT_ID;
const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
const privateKey = process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n');

function base64Url(value) {
    return Buffer.from(value).toString('base64url');
}

async function getAccessToken() {
    const now = Math.floor(Date.now() / 1000);
    const unsignedToken = [
        base64Url(JSON.stringify({ alg: 'RS256', typ: 'JWT' })),
        base64Url(JSON.stringify({
            iss: clientEmail,
            scope: 'https://www.googleapis.com/auth/firebase.messaging',
            aud: 'https://oauth2.googleapis.com/token',
            iat: now,
            exp: now + 3600,
        })),
    ].join('.');

    const signer = crypto.createSign('RSA-SHA256');
    signer.update(unsignedToken);
    signer.end();
    const signature = signer.sign(privateKey).toString('base64url');

    const response = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            assertion: `${unsignedToken}.${signature}`,
        }),
    });

    if (!response.ok) {
        throw new Error(
            `Google OAuth request failed (${response.status}): ${await response.text()}`
        );
    }

    return (await response.json()).access_token;
}

async function notifyAdmin() {
    if (!projectId || !clientEmail || !privateKey) {
        throw new Error('Firebase notification credentials are missing.');
    }

    const runUrl = `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`;
    const accessToken = await getAccessToken();
    const response = await fetch(
        `https://fcm.googleapis.com/v1/projects/${projectId}/messages:send`,
        {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${accessToken}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: {
                    topic: 'admin-app',
                    notification: {
                        title: 'Palki Sahib GitHub run failed',
                        body: 'Please check the failed GitHub Actions run.',
                    },
                    data: {
                        run_url: runUrl,
                        repository: process.env.GITHUB_REPOSITORY || '',
                        run_id: process.env.GITHUB_RUN_ID || '',
                    },
                },
            }),
        }
    );

    if (!response.ok) {
        throw new Error(
            `FCM notification failed (${response.status}): ${await response.text()}`
        );
    }

    console.log('Failure notification sent to the admin-app topic.');
}

notifyAdmin().catch((error) => {
    console.error(`Could not send admin failure notification: ${error.message}`);
    process.exitCode = 1;
});
