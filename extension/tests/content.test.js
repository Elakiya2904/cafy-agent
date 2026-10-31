import { describe, it, expect, beforeEach } from "vitest";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const cafy = require("../content.js");

const FORM = `
<form>
  <label for="fn">First Name *</label><input id="fn" name="first_name" required>
  <label>Last Name <input name="last_name"></label>
  <label for="em">Email</label><input id="em" type="email" name="email" aria-required="true">
  <input type="text" aria-label="Phone number" name="phone">
  <label for="c">Country</label>
  <select id="c" name="country"><option value="">Select…</option><option value="gb">United Kingdom</option><option value="fr">France</option></select>
  <fieldset><legend>Do you require visa sponsorship?</legend>
    <label><input type="radio" name="visa" value="y"> Yes</label><label><input type="radio" name="visa" value="n"> No</label></fieldset>
  <label for="why">Why do you want to work here?</label><textarea id="why" name="why"></textarea>
  <label for="cv">Resume/CV</label><input id="cv" type="file" name="resume" style="display:none">
  <input type="hidden" name="token" value="abc"><input type="password" name="pw">
  <button type="submit">Submit Application</button>
</form>`;

describe("cafy content script", () => {
  beforeEach(() => { document.body.innerHTML = FORM; });

  it("detects ATS from hostname", () => {
    expect(cafy.detectAts("boards.greenhouse.io")).toBe("greenhouse");
    expect(cafy.detectAts("jobs.lever.co")).toBe("lever");
    expect(cafy.detectAts("acme.wd5.myworkdayjobs.com")).toBe("workday");
    expect(cafy.detectAts("careers.example.com")).toBe("generic");
  });

  it("extracts labels, types, required flags and options; skips hidden/password", () => {
    const { fields } = cafy.collectFields(document);
    const by = Object.fromEntries(fields.map((f) => [f.key, f]));
    expect(by.first_name).toMatchObject({ label: "First Name", required: true, type: "text" });
    expect(by.last_name.label).toBe("Last Name");
    expect(by.email).toMatchObject({ type: "email", required: true });
    expect(by.phone.label).toBe("Phone number");
    expect(by.country).toMatchObject({ type: "select", options: ["United Kingdom", "France"] });
    expect(by.visa).toMatchObject({ type: "radio", label: "Do you require visa sponsorship?", options: ["Yes", "No"] });
    expect(by.resume.type).toBe("file");
    expect(by.why.label).toBe("Why do you want to work here?");
    expect(by.token).toBeUndefined();
    expect(by.pw).toBeUndefined();
  });

  it("fills empty fields, never overwrites typed text, never touches files", () => {
    const { fields, elements } = cafy.collectFields(document);
    const spec = (k) => fields.find((f) => f.key === k);
    expect(cafy.fillField(elements.first_name, spec("first_name"), "Alex")).toBe(true);
    expect(document.querySelector("[name=first_name]").value).toBe("Alex");
    document.querySelector("[name=last_name]").value = "Typed";
    expect(cafy.fillField(elements.last_name, spec("last_name"), "Smith")).toBe(false);
    expect(document.querySelector("[name=last_name]").value).toBe("Typed");
    expect(cafy.fillField(elements.country, spec("country"), "United Kingdom")).toBe(true);
    expect(document.querySelector("#c").value).toBe("gb");
    expect(cafy.fillField(elements.visa, spec("visa"), "No")).toBe(true);
    expect(document.querySelector("[name=visa][value=n]").checked).toBe(true);
    expect(cafy.fillField(elements.resume, spec("resume"), "x")).toBe(false);
  });

  it("finds the submit button without clicking it", () => {
    let clicked = false;
    document.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); clicked = true; });
    expect(cafy.findSubmitButton(document).textContent).toMatch(/Submit/);
    expect(clicked).toBe(false);
  });

  it("detects CAPTCHA widgets and validation errors", () => {
    expect(cafy.detectCaptcha(document)).toBe(false);
    document.body.insertAdjacentHTML("beforeend", '<div class="g-recaptcha" data-sitekey="k"></div><div role="alert">Email is invalid</div>');
    expect(cafy.detectCaptcha(document)).toBe(true);
    expect(cafy.collectSignals(document, "https://x/y").validation_errors).toContain("Email is invalid");
  });
});
