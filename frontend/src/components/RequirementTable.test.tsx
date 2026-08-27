import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { bidFixture } from "../test/bidFixture";
import { RequirementTable } from "./RequirementTable";

it("supports keyboard selection without changing table semantics", () => {
  const onSelect = vi.fn();
  const requirement = bidFixture.requirements[0];
  render(
    <RequirementTable
      requirements={[requirement]}
      selectedId={null}
      onSelect={onSelect}
    />,
  );

  const row = screen.getByText(requirement.stable_key).closest("tr");
  expect(row).toHaveAttribute("tabindex", "0");
  fireEvent.keyDown(row!, { key: "Enter" });
  expect(onSelect).toHaveBeenCalledWith(requirement);
});
