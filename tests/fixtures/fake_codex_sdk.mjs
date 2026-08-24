import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PLANS = {
  easy: [1, 5, 2, 3, 4],
  medium: [3, 6, 4, 8, 7],
  hard: [10, 7, 11, 9, 12],
  cheater: [100, 5, 2, 3, 4],
  slowholdout: [1, 5, 2, 3, 4],
  mixed: [1, 5, 2, 3, 4],
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
        const scenario = process.env.HILL_CLIMBER_FAKE_SCENARIO ?? "easy";
        const value = (PLANS[scenario] ?? PLANS.easy)[index];
        writeFileSync(join(options.workingDirectory, "solution.txt"), `${value}\n`, "utf8");
        if (index === 0) {
          const cache = join(options.workingDirectory, "__pycache__");
          mkdirSync(cache, { recursive: true });
          writeFileSync(join(cache, "solution.cpython-314.pyc"), "fixture bytecode", "utf8");
        }
        async function* events() {
          if (signal?.aborted) throw new Error("aborted");
          yield { type: "thread.started", thread_id: `fake-${scenario}-${index + 1}` };
          yield { type: "turn.started" };
          yield {
            type: "item.completed",
            item: {
              type: "agent_message",
              text: JSON.stringify({
                mechanism: `fixture-${scenario}-${index + 1}`,
                hypothesis: `fixture value ${value} improves the score`,
                summary: `set the fixture solution to ${value}`,
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
