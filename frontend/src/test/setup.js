// Shared test setup: the DOM matchers, and a clean localStorage between tests
// (the session token and the active production are kept there).
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  localStorage.clear();
});
