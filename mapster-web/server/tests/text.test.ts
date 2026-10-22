import { describe, expect, it } from "vitest";
import { clean, firstName } from "../src/services/text.js";

describe("clean", () => {
  it("removes dashes and exclamation marks", () => {
    expect(clean("turn-by-turn — wow!")).toBe("turn by turn, wow.");
  });
  it("tidies spaces before commas", () => {
    expect(clean("Hi Asha , hello")).toBe("Hi Asha, hello");
  });
});

describe("firstName", () => {
  it("falls back to 'there'", () => {
    expect(firstName("")).toBe("there");
    expect(firstName("Asha Rao")).toBe("Asha");
  });
});
