import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Next 16 enables this new React rule across existing client effects. Refactor those effects separately from the framework upgrade.
  { rules: { "react-hooks/set-state-in-effect": "off" } },
  globalIgnores([".next/**", "node_modules/**", "next-env.d.ts"]),
]);

export default eslintConfig;
