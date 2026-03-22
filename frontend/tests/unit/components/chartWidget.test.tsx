import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ChartWidget } from "@/components/viz/ChartWidget";

describe("ChartWidget", () => {
  it("renders chart title and supports line chart payload", () => {
    render(
      <ChartWidget
        payload={{
          title: "Revenue Trend",
          chartType: "line",
          data: [
            { month: "Jan", revenue: 100 },
            { month: "Feb", revenue: 120 },
          ],
          xAxisKey: "month",
          seriesKeys: ["revenue"],
        }}
      />,
    );

    expect(screen.getByText("Revenue Trend")).toBeInTheDocument();
  });
});
