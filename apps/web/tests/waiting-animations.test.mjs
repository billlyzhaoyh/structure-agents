import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

import {
  inferenceWaitingMarkup,
  INFERENCE_TIMELINE,
  minimumInferenceWait,
  simulationWaitingMarkup,
  STORE_TIMELINE,
} from "../waiting-animations.js";

test("inference startup depicts a synthetic relational message-passing loop", () => {
  assert.equal(INFERENCE_TIMELINE.durationMs, 10_000);
  assert.equal(INFERENCE_TIMELINE.synthetic, true);
  assert.equal(INFERENCE_TIMELINE.placeholder, true);
  assert.deepEqual(INFERENCE_TIMELINE.phases.map(({ id }) => id), [
    "tables",
    "graph",
    "messages",
    "aggregate",
    "predict",
  ]);
  assert.deepEqual(new Set(INFERENCE_TIMELINE.graphMechanisms), new Set([
    "row node",
    "typed edge",
    "foreign-key relation",
    "neighborhood sampling",
    "message passing",
    "target aggregation",
  ]));

  const markup = inferenceWaitingMarkup();
  assert.match(markup, /Inference sandbox/);
  assert.match(markup, /Relational graph message-passing animation/);
  assert.match(markup, /Synthetic placeholder flow/);
  assert.match(markup, /Shown for at least 10 seconds/);
  assert.doesNotMatch(markup, /data-inference-progress/);
  assert.doesNotMatch(markup, /RT-J/i);
});

test("inference startup enforces its minimum ten-second hold", async () => {
  let scheduledDelay = null;
  await minimumInferenceWait((complete, delay) => {
    scheduledDelay = delay;
    complete();
  });
  assert.equal(scheduledDelay, 10_000);
});

test("the frontend does not expose the implementation codename in user-facing copy", async () => {
  const appSource = await readFile(new URL("../app.js", import.meta.url), "utf8");
  assert.doesNotMatch(appSource, /RT-J/);
});

test("store wait loop covers the requested customer behaviours", async () => {
  assert.equal(STORE_TIMELINE.durationMs, 10_000);
  assert.equal(STORE_TIMELINE.synthetic, true);
  assert.equal(STORE_TIMELINE.placeholder, true);
  assert.equal(STORE_TIMELINE.checkoutStaffed, false);

  const stages = new Set(STORE_TIMELINE.agents.flatMap((agent) => (
    agent.keyframes.map(({ stage }) => stage)
  )));
  assert.equal(
    ["enter", "exit", "browse", "fitting-room", "try-on", "checkout"]
      .every((stage) => stages.has(stage)),
    true,
  );
  for (const agent of STORE_TIMELINE.agents) {
    assert.equal(agent.keyframes[0].at, 0);
    assert.equal(agent.keyframes[0].opacity, 0);
    assert.equal(agent.keyframes.at(-1).at, STORE_TIMELINE.durationMs);
    assert.equal(agent.keyframes.at(-1).opacity, 0);
    assert.deepEqual(
      agent.keyframes.map(({ at }) => at),
      [...agent.keyframes.map(({ at }) => at)].sort((left, right) => left - right),
    );
  }

  const markup = simulationWaitingMarkup();
  assert.match(markup, /Unstaffed checkout/);
  assert.match(markup, /\.\/assets\/store-background\.jpg/);
  assert.match(markup, /Entering · browsing · trying on · self-checkout · exiting/);
  assert.match(markup, /Synthetic placeholder journeys/);
  assert.doesNotMatch(markup, /data-store-(progress|elapsed)/);
  assert.doesNotMatch(markup, /store-clock/);
  assert.doesNotMatch(markup, /checkout-associate/i);
  await access(new URL("../assets/store-background.jpg", import.meta.url));
});
