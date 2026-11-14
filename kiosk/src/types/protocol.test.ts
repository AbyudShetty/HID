import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import { collectLabel, frameHeader, validateClientMessage, validateServerMessage } from "./validate";

type Json = Record<string, unknown>;
const client = samples.client as Record<string, Json>;
const server = samples.server as Record<string, Json>;
const records = samples.records as unknown as Record<string, Json>;

describe("shared protocol fixtures (also validated by pydantic in backend/tests/test_schemas.py)", () => {
  it("validates every client message", () => {
    expect(Object.keys(client).sort()).toEqual(
      ["hello", "ping", "pong", "segment.shown", "session.client_timing", "session.end", "session.request", "session.start", "stepup.request_review", "stepup.verify"].sort(),
    );
    for (const [name, msg] of Object.entries(client)) expect(validateClientMessage(msg), name).toBeNull();
  });

  it("validates every server message", () => {
    for (const [name, msg] of Object.entries(server)) expect(validateServerMessage(msg), name).toBeNull();
  });

  it("validates records", () => {
    expect(frameHeader(records.frame_header, "frame_header")).toBeNull();
    expect(collectLabel(records.collect_label_bona_fide, "label")).toBeNull();
    expect(collectLabel(records.collect_label_attack, "label")).toBeNull();
  });

  it("rejects unknown fields, wrong types, and unknown message types", () => {
    expect(validateClientMessage({ ...client.hello, surprise: 1 })).toMatch(/unknown field/);
    expect(validateClientMessage({ ...client["segment.shown"], index: "x" })).toMatch(/expected integer/);
    expect(validateClientMessage({ type: "nope" })).toMatch(/unknown message type/);
    expect(validateClientMessage(null)).toMatch(/must be an object/);
    expect(validateServerMessage({ ...server.error, code: "WHATEVER" })).toMatch(/expected one of/);
  });

  it("rejects a decision result with a missing required field", () => {
    const { flow: _flow, ...rest } = server["session.result"];
    expect(validateServerMessage(rest)).toMatch(/flow: missing/);
  });
});
