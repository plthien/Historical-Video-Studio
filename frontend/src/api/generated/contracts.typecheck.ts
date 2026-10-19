// Compile-time negative regressions against the actual generated contracts.
import type {VisualBlueprint_v1, APIRequestBodies} from "./contracts";

type Equals<A, B> = (<T>() => T extends A ? 1 : 2) extends
                     (<T>() => T extends B ? 1 : 2) ? true : false;
type Assert<T extends true> = T;

type Plan = VisualBlueprint_v1["setup_plans"][number];
type Focal = Plan["layout_control"]["focal_point"];
type T01 = Extract<Plan["template_payload"], {template_id: "T01"}>;
type Regenerate = APIRequestBodies["post__projects_project_id_voice_sections_section_id_regenerate"];

type VerifiedFocal = Assert<Equals<Focal, [number, number]>>;
type VerifiedTemplateTag = Assert<Equals<T01["template_id"], "T01">>;
type VerifiedRevision = Assert<Equals<Regenerate["expected_revision"], number>>;
type VerifiedProvider = Assert<Equals<Regenerate["provider_id"], "kokoro_local" | "elevenlabs_tts">;

const good: Focal = [0.25, 0.75];
// @ts-expect-error tuple has exactly two elements
const badLength: Focal = [0.2];
// @ts-expect-error tuple elements must be numbers
const badElement: Focal = [0.1, "oops"];
// @ts-expect-error T01 cannot be confused with another template
const badDiscriminator: T01["template_id"] = "T03";
// @ts-expect-error expected_revision is an integer-shaped numeric field
const badRevision: Regenerate["expected_revision"] = "v1";

export type CompileProof = [VerifiedFocal, VerifiedTemplateTag, VerifiedRevision, VerifiedProvider];
void good; void badLength; void badElement; void badDiscriminator; void badRevision;
