import { bench, describe } from "vitest";
import worker from "../src/index";

// Deterministic mocked bindings: no network, results sized by topK.
function makeEnv(apiKey?: string): any {
  const vector = Array.from({ length: 768 }, (_, i) => (i % 17) / 17);
  return {
    WORKER_API_KEY: apiKey,
    AI: { run: async () => ({ data: [vector] }) },
    VECTOR_INDEX: {
      query: async (_v: number[], opts: { topK: number }) => ({
        matches: Array.from({ length: opts.topK }, (_, i) => ({
          id: `doc-${i}`,
          score: 1 - i / 100,
          metadata:
            i % 3 === 0
              ? undefined
              : {
                  title: `Title ${i}`,
                  category: "API Reference",
                  source_url: `https://example.invalid/${i}`,
                  header_path: `A > B > ${i}`,
                  content: "EPLAN content chunk ".repeat(40),
                },
        })),
      }),
      insert: async (batch: unknown[]) => ({ count: batch.length }),
      describe: async () => ({ vectorCount: 12345, dimensions: 768, metric: "cosine" }),
    },
  };
}

const ctx = {} as ExecutionContext;
const BASE = "https://worker.invalid";
let sink: unknown;

async function call(env: any, path: string, init?: RequestInit) {
  const res = await worker.fetch(new Request(BASE + path, init), env, ctx);
  sink = await res.text();
  return sink;
}

function post(body: string, headers: Record<string, string> = {}): RequestInit {
  return { method: "POST", body, headers: { "Content-Type": "application/json", ...headers } };
}

describe("w1 fetch routing/CORS/404/OPTIONS", () => {
  const env = makeEnv();
  bench("OPTIONS preflight", async () => {
    await call(env, "/search", { method: "OPTIONS" });
  });
  bench("GET /health", async () => {
    await call(env, "/health");
  });
  bench("GET /stats", async () => {
    await call(env, "/stats");
  });
  bench("404 unknown path", async () => {
    await call(env, "/nope");
  });
  bench("500 error wrapper (malformed JSON on /search)", async () => {
    await call(env, "/search", post("{not json"));
  });
});

describe("w2 handleSearch by topK", () => {
  const env = makeEnv();
  const missing = JSON.stringify({});
  const bodies = [1, 5, 20, 100].map((topK) => ({
    topK,
    body: JSON.stringify({ query: "how to create a page", topK, category: "API Reference" }),
  }));
  bench("missing query -> 400", async () => {
    await call(env, "/search", post(missing));
  });
  for (const { topK, body } of bodies) {
    bench(`topK=${topK}${topK > 20 ? " (clamped to 20)" : ""}`, async () => {
      await call(env, "/search", post(body));
    });
  }
});

describe("w3 checkAuth + /add-vectors", () => {
  const body = JSON.stringify({ vectors: [{ id: "a", values: [0.1, 0.2, 0.3] }] });
  const open = makeEnv();
  const secured = makeEnv("s3cret");
  bench("no key configured (open)", async () => {
    await call(open, "/add-vectors", post(body));
  });
  bench("missing header -> 401", async () => {
    await call(secured, "/add-vectors", post(body));
  });
  bench("wrong header -> 401", async () => {
    await call(secured, "/add-vectors", post(body, { Authorization: "Bearer wrong" }));
  });
  bench("matching header -> 200", async () => {
    await call(secured, "/add-vectors", post(body, { Authorization: "Bearer s3cret" }));
  });
});

describe("w4 handleAddVectors by vector count", () => {
  const env = makeEnv();
  const empty = JSON.stringify({ vectors: [] });
  const dims = 32;
  const bodies = [10, 1000, 1001, 2500].map((n) => ({
    n,
    body: JSON.stringify({
      vectors: Array.from({ length: n }, (_, i) => ({
        id: `v-${i}`,
        values: Array.from({ length: dims }, (_, j) => ((i + j) % 11) / 11),
        metadata: i % 2 ? { title: `t${i}` } : undefined,
      })),
    }),
  }));
  bench("empty list -> 400", async () => {
    await call(env, "/add-vectors", post(empty));
  });
  for (const { n, body } of bodies) {
    bench(`vectors=${n}`, async () => {
      await call(env, "/add-vectors", post(body));
    });
  }
});

describe("w6 handleMcpRequest (createMcpServer per request)", () => {
  const env = makeEnv();
  const rpc = (method: string, params?: unknown) =>
    JSON.stringify({ jsonrpc: "2.0", id: 1, method, params });
  const initialize = rpc("initialize", {});
  const list = rpc("tools/list");
  const stats = rpc("tools/call", { name: "eplan_stats" });
  const unknownTool = rpc("tools/call", { name: "nope" });
  const unknownMethod = rpc("nope/nope");
  const searches = [1, 5, 20].map((topK) => ({
    topK,
    body: rpc("tools/call", { name: "eplan_search", arguments: { query: "macro", topK } }),
  }));
  bench("GET /mcp info", async () => {
    await call(env, "/mcp");
  });
  bench("initialize", async () => {
    await call(env, "/mcp", post(initialize));
  });
  bench("tools/list", async () => {
    await call(env, "/mcp", post(list));
  });
  bench("tools/call eplan_stats", async () => {
    await call(env, "/mcp", post(stats));
  });
  for (const { topK, body } of searches) {
    bench(`tools/call eplan_search topK=${topK}`, async () => {
      await call(env, "/sse", post(body));
    });
  }
  bench("unknown tool", async () => {
    await call(env, "/mcp", post(unknownTool));
  });
  bench("unknown method", async () => {
    await call(env, "/mcp", post(unknownMethod));
  });
});

export { sink };
