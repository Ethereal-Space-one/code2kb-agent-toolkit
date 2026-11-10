// DSH bundle plugin for the Code2KB Agent Toolkit.
//
// Registers the `code2kb` runtime skill on the host skill registry. The skill
// body is generated at load time so it carries the absolute path of the
// bundled toolkit inside this installed package: agents can read the original
// Code2KB skill workflows and run the bundled `code2kb` CLI with plain
// `python3`, with no pip installation required.
import { readFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const name = "code2kb";
export const inject = ["skills"];

const TOOLKIT_DIR = dirname(fileURLToPath(import.meta.url));
const SKILL_BODY_URL = new URL("./dsh/skill.md", import.meta.url);
const PACKAGE_URL = new URL("./package.json", import.meta.url);
const pkg = JSON.parse(readFileSync(PACKAGE_URL, "utf8"));

export function apply(ctx) {
  const content = readFileSync(SKILL_BODY_URL, "utf8").replaceAll(
    "__TOOLKIT_DIR__",
    TOOLKIT_DIR,
  );
  ctx.skills.register({
    name: "code2kb",
    description:
      "Extract evidence-checked business and engineering knowledge from pinned source revisions into a searchable knowledge base. Guides an agent through the Code2KB workflow (inventory, evidence, drafting, review) and runs the bundled code2kb CLI to check, approve, and publish governed knowledge views.",
    source: `code2kb-dsh@${pkg.version} (bundled Code2KB Agent Toolkit ${pkg.version})`,
    content,
  });
  ctx.logger.info(
    `[code2kb] registered skill "code2kb"; bundled toolkit at ${TOOLKIT_DIR}`,
  );
}
