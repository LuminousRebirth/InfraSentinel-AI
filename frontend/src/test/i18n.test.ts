import { messages } from "../i18n";

test("Chinese and English resources have identical keys", () => {
  expect(Object.keys(messages.en).sort()).toEqual(Object.keys(messages["zh-CN"]).sort());
  for (const value of Object.values(messages.en)) expect(value.trim()).not.toBe("");
  for (const value of Object.values(messages["zh-CN"])) expect(value.trim()).not.toBe("");
});
