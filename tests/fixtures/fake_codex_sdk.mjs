import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PLANS = {
  easy: [1, 5, 2, 3, 4],
  medium: [3, 6, 4, 8, 7],
  hard: [10, 7, 11, 9, 12],
  cheater: [100, 5, 2, 3, 4],
  slowholdout: [1, 5, 2, 3, 4],
  mixed: [1, 5, 2, 3, 4],
  staircase: [1, 2, 3, 4, 5],
};

export class Codex {
  constructor(options = {}) {
    if (options.env?.TOP_SECRET_FOR_CLIMB) throw new Error("candidate inherited a forbidden secret");
  }

  startThread(options) {
    return {
      async runStreamed(prompt, { signal }) {
        const delay = Number(process.env.HILL_CLIMBER_FAKE_DELAY_MS ?? 0);
        if (delay > 0) {
          await new Promise((resolve, reject) => {
            const timer = setTimeout(resolve, delay);
            signal?.addEventListener("abort", () => {
              clearTimeout(timer);
              reject(new Error("aborted"));
            }, { once: true });
          });
        }
        const match = prompt.match(/candidate (\d+)\/\d+/i);
        const index = Number(match?.[1] ?? 1) - 1;
        const round = Number(prompt.match(/round (\d+)/i)?.[1] ?? 1);
        const scenario = process.env.HILL_CLIMBER_FAKE_SCENARIO ?? "easy";
        const planValue = (PLANS[scenario] ?? PLANS.easy)[index];
        const incumbent = Number(readFileSync(join(options.workingDirectory, "solution.txt"), "utf8").trim());
        const value = scenario === "staircase" ? incumbent + planValue : planValue;
        writeFileSync(join(options.workingDirectory, "solution.txt"), `${value}\n`, "utf8");
        if (index === 0) {
          const cache = join(options.workingDirectory, "__pycache__");
          mkdirSync(cache, { recursive: true });
          writeFileSync(join(cache, "solution.cpython-314.pyc"), "fixture bytecode", "utf8");
        }
        async function* events() {
          if (signal?.aborted) throw new Error("aborted");
          yield { type: "thread.started", thread_id: `fake-${scenario}-${round}-${index + 1}` };
          yield { type: "turn.started" };
          yield {
            type: "item.completed",
            item: {
              type: "agent_message",
              text: JSON.stringify({
                mechanism: `fixture-${scenario}-${round}-${index + 1}`,
                hypothesis: `round ${round} fixture value ${value} improves the score`,
                summary: `set the round ${round} fixture solution to ${value}`,
              }),
            },
          };
          yield {
            type: "turn.completed",
            usage: {
              input_tokens: 20,
              cached_input_tokens: 0,
              output_tokens: 10,
              reasoning_output_tokens: 0,
            },
          };
        }
        return { events: events() };
      },
    };
  }
}
