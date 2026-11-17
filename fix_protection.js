// Fix: GitHub Actions reports to the Checks API, not the legacy Status API.
// Branch protection must therefore opt into checks explicitly.
const token = process.argv[2];
const OWNER = 'fanggafa';
const REPO = 'hwmon-glass';
if (!token) { console.log('no token'); process.exit(1); }

const headers = {
  Authorization: `Bearer ${token}`,
  'User-Agent': 'hwmon-ci',
  Accept: 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
};

const protection = {
  required_status_checks: {
    strict: true,
    // "app_id" is what tells GitHub these come from the Checks API
    checks: [
      { context: 'test', app_id: null },
      { context: 'lint', app_id: null },
      { context: 'sanity', app_id: null },
    ],
  },
  enforce_admins: false,
  required_pull_request_reviews: null,
  restrictions: null,
  allow_force_pushes: false,
  allow_deletions: false,
  required_conversation_resolution: false,
};

(async () => {
  const r = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/branches/main/protection`,
    { method: 'PUT', headers, body: JSON.stringify(protection) }
  );
  const t = await r.text();
  console.log('update protection:', r.status);
  if (r.status !== 200) console.log(t.slice(0, 500));

  const v = await (
    await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/branches/main/protection`, { headers })
  ).json();
  console.log('\n--- verification ---');
  console.log('checks :', JSON.stringify(v.required_status_checks?.checks));
  console.log('strict :', v.required_status_checks?.strict);
})();
