// Cron-triggered: start the nightly extract + load workflow on GitHub Actions.
// Throws on failure so the invocation shows as an error in Cloudflare's logs.

export default {
  async scheduled(controller, env, ctx) {
    const url = `https://api.github.com/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "datastack-scheduler",
      },
      body: JSON.stringify({ ref: env.REF }),
    });
    // GitHub answers 204 No Content when the run is queued.
    if (res.status !== 204) {
      throw new Error(`workflow_dispatch failed: ${res.status} ${await res.text()}`);
    }
    console.log(`dispatched ${env.WORKFLOW} on ${env.REF} (cron ${controller.cron})`);
  },
};
