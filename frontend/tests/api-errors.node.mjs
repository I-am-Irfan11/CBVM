import { test } from "node:test";
import assert from "node:assert/strict";
import { readResponse } from "../src/services/api.js";

test("server failures never expose raw server text or internal details", async () => {
  for (const body of [
    "Internal Server Error",
    "<html>Proxy failure</html>",
    JSON.stringify({ detail: "private backend exception" }),
  ]) {
    await assert.rejects(
      readResponse(new Response(body, { status: 500 })),
      (error) => {
        assert.equal(error.status, 500);
        assert.equal(
          error.message,
          "The service is temporarily unavailable. Please try again shortly.",
        );
        return true;
      },
    );
  }
});

test("review outcomes remain actionable successful responses", async () => {
  const payload = {
    results: [{ outcome: "review", review: { reason: "Low confidence" } }],
  };
  assert.deepEqual(
    await readResponse(new Response(JSON.stringify(payload))),
    payload,
  );
});

test("invalid successful response cannot be mistaken for a scan with no plates", async () => {
  await assert.rejects(
    readResponse(new Response("<html>Unavailable</html>")),
    /incomplete response/,
  );
});

test("validation feedback remains readable", async () => {
  await assert.rejects(
    readResponse(
      new Response(
        JSON.stringify({
          detail: [{ loc: ["body", "plate"], msg: "Required" }],
        }),
        { status: 422 },
      ),
    ),
    /plate: Required/,
  );
});
