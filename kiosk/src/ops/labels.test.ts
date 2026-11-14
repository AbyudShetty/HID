import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import { collectLabel } from "../types/validate";
import { buildLabel, DEFAULT_FORM, SPECIES_BY_FAMILY, type LabelForm } from "./labels";

const ok: LabelForm = { ...DEFAULT_FORM, subject_id: "S001", presenter_id: "S001", consent_id: "C-2026-001", operator: "op1" };
const attack: LabelForm = {
  ...ok,
  cls: "attack",
  pai_family: "screen_photo",
  pai_species: "screen_phone_oled",
  instrument_id: "phone_A",
  capture_procedure: "on_the_spot_phone",
};

describe("labels", () => {
  it("species catalog equals the server's (shared fixture)", () => {
    expect(SPECIES_BY_FAMILY).toEqual(samples.records.species_by_family);
  });

  it("builds a bona fide label that passes the wire validator", () => {
    const r = buildLabel(ok);
    expect("label" in r).toBe(true);
    if ("label" in r) {
      expect(collectLabel(r.label, "label")).toBeNull();
      expect(r.label).toMatchObject({ class: "bona_fide", enrolled: true, instrument_id: null, distance_cm: 50 });
    }
  });

  it("builds an attack label that passes the wire validator", () => {
    const r = buildLabel(attack);
    expect("label" in r && collectLabel(r.label, "label")).toBeNull();
  });

  it("reports every problem a collector could make", () => {
    expect(buildLabel({ ...ok, consent_id: "" })).toMatchObject({ errors: [expect.stringContaining("consent_id")] });
    expect(buildLabel({ ...attack, pai_species: "print_matte_a4" })).toMatchObject({ errors: [expect.stringContaining("belonging to the family")] });
    expect(buildLabel({ ...attack, instrument_id: "" })).toMatchObject({ errors: [expect.stringContaining("instrument_id")] });
    expect(buildLabel({ ...ok, pai_family: "print", pai_species: "print_matte_a4" })).toMatchObject({ errors: [expect.stringContaining("no attack")] });
    expect(buildLabel({ ...ok, distance_cm: "5" })).toMatchObject({ errors: [expect.stringContaining("distance_cm")] });
    expect(buildLabel({ ...attack, capture_procedure: "redteam" })).toMatchObject({ errors: [expect.stringContaining("redteam_")] });
    const red = buildLabel({ ...attack, capture_procedure: "redteam", pai_species: "redteam_flashlight" });
    expect("label" in red).toBe(true);
  });
});
