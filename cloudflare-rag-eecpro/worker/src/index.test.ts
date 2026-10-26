import { describe, it, expect, vi, beforeEach } from "vitest";
import worker from "./index";

interface FakeMatch {
  id: string;
  score: number;
  metadata?: Record<string, string>;
}

interface Fakes {
  aiRun: ReturnType<typeof vi.fn>;
  query: ReturnType<typeof vi.fn>;
  insert: ReturnType<typeof vi.fn>;
  describe: ReturnType<typeof vi.fn>;
}

const QUERY_VECTOR = [0.1, 0.2, 0.3];

function makeEnv(opts: { apiKey?: string; matches?: FakeMatch[] } = {}): {
  env: Env;
  fakes: Fakes;
} {
  const fakes: Fakes = {
    aiRun: vi.fn(async () => ({ data: [QUERY_VECTOR] })),
    query: vi.fn(async () => ({ matches: opts.matches ?? [], count: (opts.matches ?? []).length })),
    insert: vi.fn(async () => ({ mutationId: "m1" })),
    describe: vi.fn(async () => ({ vectorCount: 42 })),
  };
  const env = {
    AI: { run: fakes.aiRun },
    VECTOR_INDEX: {
      query: fakes.query,
      insert: fakes.insert,
      describe: fakes.describe,
    },
    ...(opts.apiKey !== undefined ? { WORKER_API_KEY: opts.apiKey } : {}),
  } as unknown as Env;
  return { env, fakes };
}

const ctx = {} as ExecutionContext;

function post(path: string, body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://worker.example${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

async function call(req: Request, env: Env): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await worker.fetch(req, env, ctx);
  return { status: res.status, body: (await res.json()) as Record<string, unknown> };
}

function vectors(n: number) {
  return Array.from({ length: n }, (_, i) => ({ id: `v${i}`, values: [i, i + 1] }));
}

describe("checkAuth (via POST /add-vectors)", () => {
  it("allows requests when WORKER_API_KEY is not configured (B27)", async () => {
    const { env, fakes } = makeEnv();
    const { status, body } = await call(post("/add-vectors", { vectors: vectors(1) }), env);
    expect(status).toBe(200);
    expect(body).toEqual({ success: true, inserted: 1 });
    expect(fakes.insert).toHaveBeenCalledTimes(1);
  });

  it("allows requests when WORKER_API_KEY is an empty string", async () => {
    const { env } = makeEnv({ apiKey: "" });
    const { status } = await call(post("/add-vectors", { vectors: vectors(1) }), env);
    expect(status).toBe(200);
  });

  it("passes with the exact 'Bearer <key>' header (B28)", async () => {
    const { env, fakes } = makeEnv({ apiKey: "s3cret" });
    const { status, body } = await call(
      post("/add-vectors", { vectors: vectors(2) }, { Authorization: "Bearer s3cret" }),
      env
    );
    expect(status).toBe(200);
    expect(body).toEqual({ success: true, inserted: 2 });
    expect(fakes.insert).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["missing header", undefined],
    ["wrong key", "Bearer wrong"],
    ["key without Bearer prefix", "s3cret"],
    ["lowercase scheme", "bearer s3cret"],
    ["trailing whitespace", "Bearer s3cret "],
    ["extra space", "Bearer  s3cret"],
    ["key prefix only", "Bearer s3cre"],
    ["Basic scheme", "Basic s3cret"],
  ])("rejects %s with 401 (B28)", async (_label, header) => {
    const { env, fakes } = makeEnv({ apiKey: "s3cret" });
    const headers: Record<string, string> = header === undefined ? {} : { Authorization: header };
    const { status, body } = await call(post("/add-vectors", { vectors: vectors(1) }, headers), env);
    expect(status).toBe(401);
    expect(String(body.error)).toMatch(/^Unauthorized/);
    expect(fakes.insert).not.toHaveBeenCalled();
  });

  it("returns a JSON content type on 401", async () => {
    const { env } = makeEnv({ apiKey: "s3cret" });
    const res = await worker.fetch(post("/add-vectors", { vectors: vectors(1) }), env, ctx);
    expect(res.status).toBe(401);
    expect(res.headers.get("Content-Type")).toBe("application/json");
  });
});

describe("handleSearch (POST /search)", () => {
  it.each([
    ["missing query", {}],
    ["empty query", { query: "" }],
  ])("returns 400 for %s (B29)", async (_label, payload) => {
    const { env, fakes } = makeEnv();
    const { status, body } = await call(post("/search", payload), env);
    expect(status).toBe(400);
    expect(body).toEqual({ error: "Missing 'query' field" });
    expect(fakes.aiRun).not.toHaveBeenCalled();
    expect(fakes.query).not.toHaveBeenCalled();
  });

  it("embeds the query and defaults topK to 5 without a filter (B30)", async () => {
    const { env, fakes } = makeEnv();
    await call(post("/search", { query: "formula editor" }), env);
    expect(fakes.aiRun).toHaveBeenCalledWith("@cf/baai/bge-base-en-v1.5", { text: ["formula editor"] });
    expect(fakes.query).toHaveBeenCalledTimes(1);
    const [vec, opts] = fakes.query.mock.calls[0] as [number[], Record<string, unknown>];
    expect(vec).toEqual(QUERY_VECTOR);
    expect(opts.topK).toBe(5);
    expect(opts.returnMetadata).toBe("all");
    expect(opts.returnValues).toBe(false);
    expect(opts).not.toHaveProperty("filter");
  });

  it.each([
    [1, 1],
    [19, 19],
    [20, 20],
    [21, 20],
    [1000, 20],
  ])("passes topK=%i as %i (cap at 20) (B30)", async (requested, expected) => {
    const { env, fakes } = makeEnv();
    await call(post("/search", { query: "q", topK: requested }), env);
    const [, opts] = fakes.query.mock.calls[0] as [number[], Record<string, unknown>];
    expect(opts.topK).toBe(expected);
  });

  it("filters by category equality when category is given (B30)", async () => {
    const { env, fakes } = makeEnv();
    await call(post("/search", { query: "q", category: "eecplc" }), env);
    const [, opts] = fakes.query.mock.calls[0] as [number[], Record<string, unknown>];
    expect(opts.filter).toEqual({ category: { $eq: "eecplc" } });
  });

  it("does not filter when category is an empty string", async () => {
    const { env, fakes } = makeEnv();
    await call(post("/search", { query: "q", category: "" }), env);
    const [, opts] = fakes.query.mock.calls[0] as [number[], Record<string, unknown>];
    expect(opts).not.toHaveProperty("filter");
  });

  it("returns {query, results, count} with mapped metadata (B30)", async () => {
    const { env } = makeEnv({
      matches: [
        {
          id: "a",
          score: 0.91,
          metadata: {
            title: "Title A",
            category: "refformulas",
            source: "a.md",
            content: "body A",
            header_path: "H1 > H2",
          },
        },
        { id: "b", score: 0.5 },
        { id: "c", score: 0.4, metadata: { title: "Only title" } },
      ],
    });
    const res = await worker.fetch(post("/search", { query: "abc" }), env, ctx);
    expect(res.status).toBe(200);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("*");
    const body = (await res.json()) as {
      query: string;
      count: number;
      results: Array<Record<string, unknown>>;
    };
    expect(body.query).toBe("abc");
    expect(body.count).toBe(3);
    expect(body.results).toHaveLength(3);
    expect(body.results[0]).toMatchObject({
      id: "a",
      score: 0.91,
      title: "Title A",
      category: "refformulas",
      source: "a.md",
      content: "body A",
      header_path: "H1 > H2",
    });
    expect(body.results[1]).toMatchObject({
      id: "b",
      score: 0.5,
      title: "",
      category: "",
      source: "",
      content: "",
      header_path: "",
    });
    expect(body.results[2]).toMatchObject({
      id: "c",
      title: "Only title",
      category: "",
      source: "",
      content: "",
      header_path: "",
    });
  });

  it("returns an empty result list with count 0", async () => {
    const { env } = makeEnv({ matches: [] });
    const { status, body } = await call(post("/search", { query: "nothing" }), env);
    expect(status).toBe(200);
    expect(body).toEqual({ query: "nothing", results: [], count: 0 });
  });

  it("does not require auth even when WORKER_API_KEY is set", async () => {
    const { env } = makeEnv({ apiKey: "s3cret" });
    const { status } = await call(post("/search", { query: "q" }), env);
    expect(status).toBe(200);
  });

  it("returns 500 with the error message when the vector query fails", async () => {
    const { env, fakes } = makeEnv();
    fakes.query.mockRejectedValueOnce(new Error("vectorize down"));
    const { status, body } = await call(post("/search", { query: "q" }), env);
    expect(status).toBe(500);
    expect(body).toEqual({ error: "vectorize down" });
  });

  it("returns 500 for a malformed JSON body", async () => {
    const { env } = makeEnv();
    const req = new Request("https://worker.example/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{not json",
    });
    const res = await worker.fetch(req, env, ctx);
    expect(res.status).toBe(500);
  });

  it("is not routed for GET /search", async () => {
    const { env, fakes } = makeEnv();
    const res = await worker.fetch(new Request("https://worker.example/search"), env, ctx);
    expect(res.status).toBe(404);
    expect(fakes.query).not.toHaveBeenCalled();
  });
});

describe("handleAddVectors (POST /add-vectors)", () => {
  let env: Env;
  let fakes: Fakes;

  beforeEach(() => {
    ({ env, fakes } = makeEnv());
  });

  it.each([
    ["missing vectors", {}],
    ["empty vectors", { vectors: [] }],
  ])("returns 400 for %s (B31)", async (_label, payload) => {
    const { status, body } = await call(post("/add-vectors", payload), env);
    expect(status).toBe(400);
    expect(body).toEqual({ error: "No vectors provided" });
    expect(fakes.insert).not.toHaveBeenCalled();
  });

  it("inserts vectors with default empty metadata", async () => {
    const payload = {
      vectors: [
        { id: "x", values: [1, 2], metadata: { title: "T" } },
        { id: "y", values: [3, 4] },
      ],
    };
    const { status, body } = await call(post("/add-vectors", payload), env);
    expect(status).toBe(200);
    expect(body).toEqual({ success: true, inserted: 2 });
    expect(fakes.insert).toHaveBeenCalledWith([
      { id: "x", values: [1, 2], metadata: { title: "T" } },
      { id: "y", values: [3, 4], metadata: {} },
    ]);
  });

  it.each([
    [1000, [1000]],
    [1001, [1000, 1]],
    [2500, [1000, 1000, 500]],
  ])("inserts %i vectors in batches of 1000 (B31)", async (n, batchSizes) => {
    const { status, body } = await call(post("/add-vectors", { vectors: vectors(n) }), env);
    expect(status).toBe(200);
    expect(body).toEqual({ success: true, inserted: n });
    const sizes = fakes.insert.mock.calls.map((c) => (c[0] as unknown[]).length);
    expect(sizes).toEqual(batchSizes);
    const ids = fakes.insert.mock.calls.flatMap((c) => (c[0] as Array<{ id: string }>).map((v) => v.id));
    expect(ids).toEqual(vectors(n).map((v) => v.id));
  });

  it("returns 500 when an insert fails", async () => {
    fakes.insert.mockRejectedValueOnce(new Error("insert failed"));
    const { status, body } = await call(post("/add-vectors", { vectors: vectors(1) }), env);
    expect(status).toBe(500);
    expect(body).toEqual({ error: "insert failed" });
  });
});
