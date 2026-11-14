// Collection label helpers (plan §8.6). The species catalog is shared with the server through
// backend/tests/fixtures/protocol_samples.json (records.species_by_family), checked in labels.test.ts.
import type { CaptureProcedure, CollectLabel, Lighting, PaiFamily, SkinToneBucket } from "../types/protocol";

export const SPECIES_BY_FAMILY: Record<Exclude<PaiFamily, "none">, string[]> = {
  print: ["print_matte_a4", "print_glossy_photo", "print_cutout_eyes", "print_curved"],
  screen_photo: ["screen_phone_oled", "screen_tablet_lcd", "screen_laptop"],
  video_replay: ["replay_phone", "replay_tablet", "replay_monitor"],
  mask: ["mask_paper_flat", "mask_paper_curved", "mask_rigid_3d"],
};

export const CAPTURE_PROCEDURES: CaptureProcedure[] = ["standard", "on_the_spot_phone", "auto_repeat_rig", "redteam"];
export const LIGHTINGS: Lighting[] = ["office", "dim", "backlit", "side_lamp", "bright"];
export const SKIN_TONES: SkinToneBucket[] = ["unreported", "light", "medium", "dark"];

export interface LabelForm {
  subject_id: string;
  presenter_id: string;
  cls: "bona_fide" | "attack";
  enrolled: boolean;
  claimed_badge_id: string;
  capture_procedure: CaptureProcedure;
  pai_family: PaiFamily;
  pai_species: string;
  instrument_id: string;
  lighting: Lighting;
  distance_cm: string;
  glasses: boolean;
  skin_tone_bucket: SkinToneBucket;
  consent_id: string;
  operator: string;
  notes: string;
}

export const DEFAULT_FORM: LabelForm = {
  subject_id: "",
  presenter_id: "",
  cls: "bona_fide",
  enrolled: true,
  claimed_badge_id: "",
  capture_procedure: "standard",
  pai_family: "none",
  pai_species: "none",
  instrument_id: "",
  lighting: "office",
  distance_cm: "50",
  glasses: false,
  skin_tone_bucket: "unreported",
  consent_id: "",
  operator: "",
  notes: "",
};

/** Returns the label or a list of problems (mirrors the server rules in schemas.CollectLabel; the server re-validates). */
export function buildLabel(f: LabelForm): { label: CollectLabel } | { errors: string[] } {
  const errors: string[] = [];
  if (!f.subject_id.trim()) errors.push("subject_id is required");
  if (!f.presenter_id.trim()) errors.push("presenter_id is required");
  if (!f.consent_id.trim()) errors.push("consent_id is required (a signed consent form, docs/CONSENT_FORM.md)");
  const distance = f.distance_cm.trim() === "" ? null : Number(f.distance_cm);
  if (distance !== null && (!Number.isInteger(distance) || distance < 10 || distance > 300)) errors.push("distance_cm must be an integer 10..300");
  if (f.cls === "bona_fide") {
    if (f.pai_family !== "none" || f.pai_species !== "none") errors.push("bona fide sessions have no attack family/species");
  } else {
    if (f.pai_family === "none") errors.push("choose the attack family");
    else if (f.capture_procedure === "redteam") {
      if (!f.pai_species.startsWith("redteam_")) errors.push("red team sessions use pai_species 'redteam_<description>'");
    } else if (!SPECIES_BY_FAMILY[f.pai_family].includes(f.pai_species)) errors.push("choose a species belonging to the family");
    if (!f.instrument_id.trim()) errors.push("instrument_id is required for attacks (the specific print/device)");
  }
  if (errors.length) return { errors };
  return {
    label: {
      subject_id: f.subject_id.trim(),
      presenter_id: f.presenter_id.trim(),
      class: f.cls,
      enrolled: f.cls === "bona_fide" ? f.enrolled : null,
      claimed_badge_id: f.claimed_badge_id.trim() || null,
      capture_procedure: f.capture_procedure,
      pai_family: f.pai_family,
      pai_species: f.pai_species,
      instrument_id: f.cls === "attack" ? f.instrument_id.trim() : null,
      lighting: f.lighting,
      distance_cm: distance,
      glasses: f.glasses,
      skin_tone_bucket: f.skin_tone_bucket,
      consent_id: f.consent_id.trim(),
      operator: f.operator.trim(),
      notes: f.notes.trim(),
    },
  };
}
