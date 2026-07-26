/** @type {import('jest').Config} */
module.exports = {
  // NOTE: deliberately NOT using next/jest's nextJest() wrapper here.
  // That wrapper's transform pipeline loads Next's native SWC addon
  // (@next/swc-*), which crashes with a Bus error / SIGBUS in the
  // sandbox this was built in - reproduces even on a bare
  // `require("@next/swc-linux-arm64-gnu")`, unrelated to app code.
  // ts-jest compiles via the pure-JS TypeScript compiler instead, so
  // there's no native binary to crash on. This only affects the
  // local *test* transform; `next build`/`next dev` still use SWC
  // as normal outside of Jest.
  testEnvironment: "jest-environment-jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  transform: {
    "^.+\\.tsx?$": ["ts-jest", { tsconfig: "<rootDir>/tsconfig.json", jsx: "react-jsx" }],
  },
};
