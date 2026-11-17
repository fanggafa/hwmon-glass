// Applies branch protection to main so nothing lands without a green PR.
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
    strict: true,              // branch must be up to date with main
    contexts: ['test', 'lint', 'sanity'],
  },
  enforce_admins: false,       // the owner can still push in an emergency
  required_pull_request_reviews: {
    required_approving_review_count: 0,  // solo project: no second reviewer
    dismiss_stale_reviews: false,
  },
  restrictions: null,
  allow_force_pushes: false,
  allow_deletions: false,
  required_conversation_resolution: true,
};

(async () => {
  // 1. branch protection
  let r = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/branches/main/protection`,
    { method: 'PUT', headers, body: JSON.stringify(protection) }
  );
  let t = await r.text();
  console.log('branch protection:', r.status);
  if (r.status !== 200) console.log('  ', t.slice(0, 500));

  // 2. repo hygiene: squash merge only, delete branch after merge
  r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}`, {
    method: 'PATCH', headers,
    body: JSON.stringify({
      allow_squash_merge: true,
      allow_merge_commit: false,
      allow_rebase_merge: false,
      squash_merge_commit_title: 'PR_TITLE',
      squash_merge_commit_message: 'PR_BODY',
      delete_branch_on_merge: true,
      has_wiki: false,
    }),
  });
  t = await r.text();
  console.log('repo settings:', r.status);
  if (r.status !== 200) console.log('  ', t.slice(0, 400));

  // 3. enable Actions (in case they are off)
  r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/actions/permissions`, {
    method: 'PUT', headers,
    body: JSON.stringify({ enabled: true, allowed_actions: 'all' }),
  });
  console.log('actions permissions:', r.status);

  // verify
  r = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/branches/main/protection`, { headers }
  );
  const j = await r.json();
  console.log('\n--- verification ---');
  console.log('required checks:', JSON.stringify(j.required_status_checks?.contexts));
  console.log('strict          :', j.required_status_checks?.strict);
  console.log('force push      :', j.allow_force_pushes?.enabled);
  console.log('deletions       :', j.allow_deletions?.enabled);
})();
