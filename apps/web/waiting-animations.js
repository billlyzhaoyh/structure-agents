export const INFERENCE_TIMELINE = {
  synthetic: true,
  placeholder: true,
  durationMs: 10_000,
  phases: [
    { at: 0, id: "tables", label: "Reading relational tables" },
    { at: 2_000, id: "graph", label: "Building the graph" },
    { at: 4_000, id: "messages", label: "Passing typed messages" },
    { at: 6_000, id: "aggregate", label: "Aggregating at the target" },
    { at: 8_000, id: "predict", label: "Preparing the prediction" },
  ],
  graphMechanisms: [
    "row node",
    "typed edge",
    "foreign-key relation",
    "neighborhood sampling",
    "message passing",
    "target aggregation",
  ],
};

export const STORE_TIMELINE = {
  synthetic: true,
  placeholder: true,
  durationMs: 10_000,
  checkoutStaffed: false,
  agents: [
    {
      id: "shopper-01",
      colour: "amber",
      keyframes: [
        { at: 0, x: 50, y: 108, opacity: 0, stage: "off-stage" },
        { at: 600, x: 50, y: 91, opacity: 1, stage: "enter" },
        { at: 2_300, x: 25, y: 61, opacity: 1, stage: "browse" },
        { at: 4_400, x: 25, y: 61, opacity: 1, stage: "browse" },
        { at: 6_100, x: 78, y: 28, opacity: 1, stage: "checkout" },
        { at: 7_700, x: 78, y: 28, opacity: 1, stage: "checkout" },
        { at: 9_200, x: 50, y: 94, opacity: 1, stage: "exit" },
        { at: 10_000, x: 50, y: 108, opacity: 0, stage: "off-stage" },
      ],
    },
    {
      id: "shopper-02",
      colour: "violet",
      keyframes: [
        { at: 0, x: 47, y: 108, opacity: 0, stage: "off-stage" },
        { at: 1_200, x: 47, y: 92, opacity: 1, stage: "enter" },
        { at: 2_800, x: 61, y: 63, opacity: 1, stage: "browse" },
        { at: 4_100, x: 51, y: 20, opacity: 1, stage: "fitting-room" },
        { at: 4_700, x: 51, y: 14, opacity: 0, stage: "try-on" },
        { at: 5_500, x: 51, y: 14, opacity: 0, stage: "try-on" },
        { at: 5_900, x: 51, y: 20, opacity: 1, stage: "new-outfit" },
        { at: 7_000, x: 74, y: 28, opacity: 1, stage: "checkout" },
        { at: 8_200, x: 74, y: 28, opacity: 1, stage: "checkout" },
        { at: 9_400, x: 51, y: 94, opacity: 1, stage: "exit" },
        { at: 10_000, x: 51, y: 108, opacity: 0, stage: "off-stage" },
      ],
    },
    {
      id: "shopper-03",
      colour: "blue",
      keyframes: [
        { at: 0, x: 53, y: 108, opacity: 0, stage: "off-stage" },
        { at: 2_000, x: 53, y: 93, opacity: 1, stage: "enter" },
        { at: 3_500, x: 81, y: 65, opacity: 1, stage: "browse" },
        { at: 5_600, x: 81, y: 65, opacity: 1, stage: "browse" },
        { at: 7_300, x: 55, y: 89, opacity: 1, stage: "exit" },
        { at: 8_200, x: 53, y: 108, opacity: 0, stage: "off-stage" },
        { at: 10_000, x: 53, y: 108, opacity: 0, stage: "off-stage" },
      ],
    },
    {
      id: "shopper-04",
      colour: "green",
      keyframes: [
        { at: 0, x: 49, y: 108, opacity: 0, stage: "off-stage" },
        { at: 3_300, x: 49, y: 93, opacity: 1, stage: "enter" },
        { at: 4_800, x: 39, y: 45, opacity: 1, stage: "browse" },
        { at: 6_600, x: 39, y: 45, opacity: 1, stage: "browse" },
        { at: 8_300, x: 49, y: 93, opacity: 1, stage: "exit" },
        { at: 9_100, x: 49, y: 108, opacity: 0, stage: "off-stage" },
        { at: 10_000, x: 49, y: 108, opacity: 0, stage: "off-stage" },
      ],
    },
    {
      id: "shopper-05",
      colour: "coral",
      keyframes: [
        { at: 0, x: 46, y: 108, opacity: 0, stage: "off-stage" },
        { at: 700, x: 46, y: 93, opacity: 1, stage: "enter" },
        { at: 2_000, x: 20, y: 45, opacity: 1, stage: "browse" },
        { at: 3_500, x: 20, y: 45, opacity: 1, stage: "browse" },
        { at: 5_100, x: 70, y: 30, opacity: 1, stage: "checkout" },
        { at: 6_400, x: 70, y: 30, opacity: 1, stage: "checkout" },
        { at: 8_000, x: 54, y: 90, opacity: 1, stage: "exit" },
        { at: 8_900, x: 54, y: 108, opacity: 0, stage: "off-stage" },
        { at: 10_000, x: 54, y: 108, opacity: 0, stage: "off-stage" },
      ],
    },
  ],
};

export function minimumInferenceWait(schedule = setTimeout) {
  return new Promise((resolve) => schedule(resolve, INFERENCE_TIMELINE.durationMs));
}

export function inferenceWaitingMarkup() {
  return `<section class="sandbox-wait sandbox-wait--inference" aria-label="Inference sandbox starting">
    <header><div><span class="waiting-pulse" aria-hidden="true"></span><p><small>Inference sandbox</small><b>Starting a relational inference run</b></p></div><i data-inference-phase aria-live="polite">Reading relational tables</i></header>
    <div class="graph-animation" data-inference-animation data-phase="tables">
      <svg viewBox="0 0 900 390" role="img" aria-labelledby="inference-animation-title inference-animation-description">
        <title id="inference-animation-title">Relational graph message-passing animation</title>
        <desc id="inference-animation-description">Synthetic customer, transaction, and article records exchange typed messages before aggregation at a target node.</desc>
        <defs><filter id="waiting-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="5" result="blur"></feGaussianBlur><feMerge><feMergeNode in="blur"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge></filter></defs>
        <g class="graph-routes" aria-hidden="true">
          <path id="route-customer-transaction" class="relation" d="M 190 104 C 270 104, 270 195, 350 195"></path>
          <path id="route-article-transaction" class="relation" d="M 190 286 C 270 286, 270 210, 350 210"></path>
          <path id="route-customer-target" class="message-route" d="M 190 96 C 370 55, 470 105, 565 164"></path>
          <path id="route-transaction-target" class="message-route" d="M 500 203 C 525 203, 540 195, 565 195"></path>
          <path id="route-article-target" class="message-route" d="M 190 294 C 370 335, 470 275, 565 226"></path>
          <circle class="graph-signal relation-signal" data-route="route-customer-transaction" r="6"></circle>
          <circle class="graph-signal relation-signal" data-route="route-article-transaction" r="6"></circle>
          <circle class="graph-signal message-signal" data-route="route-customer-target" r="5"></circle>
          <circle class="graph-signal message-signal" data-route="route-transaction-target" r="5"></circle>
          <circle class="graph-signal message-signal" data-route="route-article-target" r="5"></circle>
        </g>
        <g class="graph-table customer-table" transform="translate(35 52)"><rect width="155" height="96" rx="8"></rect><text x="15" y="25">CUSTOMERS</text><text class="graph-row" x="15" y="54">C_104 · ACTIVE</text><text class="graph-row" x="15" y="78">C_219 · MEMBER</text></g>
        <g class="graph-table transaction-table" transform="translate(350 150)"><rect width="150" height="106" rx="8"></rect><text x="15" y="25">TRANSACTIONS</text><text class="graph-row" x="15" y="54">T_8821 · C_104</text><text class="graph-row" x="15" y="78">A_501 · £0.032</text></g>
        <g class="graph-table article-table" transform="translate(35 242)"><rect width="155" height="96" rx="8"></rect><text x="15" y="25">ARTICLES</text><text class="graph-row" x="15" y="54">A_501 · KNITWEAR</text><text class="graph-row" x="15" y="78">A_882 · DRESS</text></g>
        <g class="target-node" transform="translate(565 105)"><rect width="145" height="180" rx="10"></rect><text class="target-kicker" x="72" y="30" text-anchor="middle">TARGET NODE</text><text class="target-title" x="72" y="58" text-anchor="middle">GRAPH ML</text>${Array.from({ length: 8 }, (_, index) => `<rect class="embedding-bar" x="22" y="${76 + index * 11}" width="101" height="7" rx="2"></rect>`).join("")}<text class="target-caption" x="72" y="169" text-anchor="middle">AGGREGATE</text></g>
        <path id="route-target-output" class="output-route" d="M 710 195 C 735 195, 750 195, 775 195"></path><circle class="graph-signal output-signal" data-route="route-target-output" r="6"></circle>
        <g class="prediction-node" transform="translate(775 145)"><rect width="95" height="100" rx="9"></rect><text x="47" y="28" text-anchor="middle">7-DAY SALES</text><text class="prediction-value" x="47" y="62" text-anchor="middle">…</text><text x="47" y="84" text-anchor="middle">PREPARING</text></g>
      </svg>
    </div>
    <footer><span>Synthetic placeholder flow</span><span>Shown for at least 10 seconds</span></footer>
  </section>`;
}

export function simulationWaitingMarkup() {
  return `<section class="sandbox-wait sandbox-wait--simulation" aria-label="Simulation sandbox starting">
    <header><div><span class="waiting-pulse" aria-hidden="true"></span><p><small>Simulation sandbox</small><b>Testing customer flow through the store</b></p></div><i aria-live="polite">Waiting for the simulation</i></header>
    <div class="pixel-store" data-store-animation>
      <img class="store-background" src="./assets/store-background.jpg" alt="Top-down pixel-art fashion store with clothing displays, fitting rooms, and an unstaffed checkout" width="1672" height="941">
      <div class="store-shade" aria-hidden="true"></div>
      <div class="store-location store-location--fitting">Fitting rooms</div>
      <div class="store-location store-location--checkout">Unstaffed checkout</div>
      <div class="store-location store-location--entrance">Entrance</div>
      <div class="store-agents" aria-hidden="true">${STORE_TIMELINE.agents.map((agent) => `<div class="pixel-shopper pixel-shopper--${agent.colour}" data-agent-id="${agent.id}"><span></span><b></b><i></i><em></em><small></small></div>`).join("")}</div>
    </div>
    <footer><span>Illustrative customer flow</span><span>Entering · browsing · trying on · self-checkout · exiting</span></footer>
    <p class="waiting-disclaimer">Synthetic placeholder journeys; they are not observations or simulation results.</p>
  </section>`;
}

function clamp(value) {
  return Math.min(1, Math.max(0, value));
}

function smoothstep(value) {
  const bounded = clamp(value);
  return bounded * bounded * (3 - 2 * bounded);
}

function phaseAt(time) {
  const index = Math.max(0, INFERENCE_TIMELINE.phases.findLastIndex((phase) => phase.at <= time));
  return { phase: INFERENCE_TIMELINE.phases[index], index };
}

function positionSignal(signal, progress) {
  const path = document.getElementById(signal.dataset.route);
  if (!path) return;
  const point = path.getPointAtLength(path.getTotalLength() * clamp(progress));
  signal.setAttribute("transform", `translate(${point.x} ${point.y})`);
}

function animateInference(root) {
  const scene = root.querySelector("[data-inference-animation]");
  if (!scene) return () => {};
  const phaseLabel = root.querySelector("[data-inference-phase]");
  const signals = [...root.querySelectorAll(".graph-signal")];
  const bars = [...root.querySelectorAll(".embedding-bar")];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const startedAt = performance.now();
  let frameId;

  const render = (time) => {
    const current = phaseAt(time);
    scene.dataset.phase = current.phase.id;
    phaseLabel.textContent = current.phase.label;
    signals.forEach((signal, index) => {
      let signalProgress = 0;
      let visible = false;
      if (signal.classList.contains("relation-signal") && current.phase.id === "graph") {
        signalProgress = ((time - 2_000) / 1_100 + index * 0.42) % 1;
        visible = true;
      } else if (signal.classList.contains("message-signal") && current.phase.id === "messages") {
        signalProgress = ((time - 4_000) / 1_250 + index * 0.24) % 1;
        visible = true;
      } else if (signal.classList.contains("output-signal") && current.phase.id === "predict") {
        signalProgress = (time - 8_000) / 800;
        visible = signalProgress < 1;
      }
      positionSignal(signal, signalProgress);
      signal.style.opacity = visible ? "1" : "0";
    });
    const activeBars = current.phase.id === "aggregate"
      ? Math.ceil(smoothstep((time - 6_000) / 1_800) * bars.length)
      : current.phase.id === "predict" ? bars.length : 0;
    bars.forEach((bar, index) => bar.classList.toggle("is-active", index < activeBars));
  };
  const tick = (now) => {
    render((now - startedAt) % INFERENCE_TIMELINE.durationMs);
    frameId = window.requestAnimationFrame(tick);
  };
  render(reducedMotion ? 8_800 : 0);
  if (!reducedMotion) frameId = window.requestAnimationFrame(tick);
  return () => window.cancelAnimationFrame(frameId);
}

function storeStateAt(keyframes, time) {
  const nextIndex = keyframes.findIndex((frame) => frame.at > time);
  if (nextIndex < 0) return { ...keyframes.at(-1), moving: false };
  const previous = keyframes[Math.max(0, nextIndex - 1)];
  const next = keyframes[nextIndex];
  const amount = smoothstep((time - previous.at) / Math.max(1, next.at - previous.at));
  return {
    x: previous.x + (next.x - previous.x) * amount,
    y: previous.y + (next.y - previous.y) * amount,
    opacity: previous.opacity + (next.opacity - previous.opacity) * amount,
    stage: previous.stage,
    moving: Math.hypot(next.x - previous.x, next.y - previous.y) > 2 && previous.opacity > 0.2 && next.opacity > 0.2,
  };
}

function animateStore(root, onComplete) {
  const scene = root.querySelector("[data-store-animation]");
  if (!scene) return () => {};
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const startedAt = performance.now();
  let frameId;
  let completed = false;

  const render = (time) => {
    STORE_TIMELINE.agents.forEach((agent, index) => {
      const node = scene.querySelector(`[data-agent-id="${agent.id}"]`);
      const current = storeStateAt(agent.keyframes, time);
      node.style.left = `${current.x}%`;
      node.style.top = `${current.y}%`;
      node.style.opacity = current.opacity.toFixed(3);
      node.style.zIndex = String(Math.round(current.y) + index);
      node.dataset.stage = current.stage;
      node.classList.toggle("is-moving", current.moving);
      node.querySelector("small").textContent = {
        browse: "Browsing",
        checkout: "Self-checkout",
        "fitting-room": "Trying on",
        "try-on": "Trying on",
        "new-outfit": "New outfit",
      }[current.stage] ?? "";
    });
  };
  const tick = (now) => {
    const time = now - startedAt;
    render(Math.min(time, STORE_TIMELINE.durationMs));
    if (time >= STORE_TIMELINE.durationMs) {
      if (!completed) {
        completed = true;
        onComplete?.();
      }
      return;
    }
    frameId = window.requestAnimationFrame(tick);
  };
  render(reducedMotion ? 5_900 : 0);
  if (reducedMotion) {
    frameId = window.setTimeout(() => onComplete?.(), 250);
    return () => window.clearTimeout(frameId);
  }
  frameId = window.requestAnimationFrame(tick);
  return () => window.cancelAnimationFrame(frameId);
}

export function startWaitingAnimations({ onSimulationComplete } = {}) {
  const cleanups = [animateInference(document), animateStore(document, onSimulationComplete)];
  return () => cleanups.forEach((cleanup) => cleanup());
}
