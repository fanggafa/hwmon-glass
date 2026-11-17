const token = process.argv[2];
const h = { Authorization: `Bearer ${token}`, 'User-Agent': 'h', Accept: 'application/vnd.github+json' };

(async () => {
  const pr = await (await fetch('https://api.github.com/repos/fanggafa/hwmon-glass/pulls/1', { headers: h })).json();
  const checks = await (
    await fetch(`https://api.github.com/repos/fanggafa/hwmon-glass/commits/${pr.head.sha}/check-runs`, { headers: h })
  ).json();

  console.log('mergeable_state:', pr.mergeable_state);
  console.log('');
  console.log('实际 check 名称:');
  for (const c of checks.check_runs) {
    console.log('   [' + c.name + '] ->', c.conclusion);
  }
})();
