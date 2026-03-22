"use client"

import React from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ChartPayload } from "@/types";

interface ChartWidgetProps {
  payload: ChartPayload;
}

const COLORS = ["#818cf8", "#34d399", "#fbbf24", "#f472b6", "#60a5fa"];

export const ChartWidget: React.FC<ChartWidgetProps> = ({ payload }) => {
  const { title, chartType: type, data, xAxisKey, seriesKeys } = payload;

  const renderChart = () => {
    switch (type) {
      case "line":
        return (
          <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis 
              dataKey={xAxisKey} 
              stroke="#94a3b8" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false} 
            />
            <YAxis 
              stroke="#94a3b8" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false} 
              tickFormatter={(value) => `${value}`}
            />
            <Tooltip 
              contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", color: "#f1f5f9" }}
              itemStyle={{ color: "#f1f5f9" }}
              cursor={{ stroke: "#475569" }}
            />
            <Legend wrapperStyle={{ paddingTop: "10px" }} />
            {seriesKeys.map((key, index) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[index % COLORS.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6 }}
              />
            ))}
          </LineChart>
        );
      case "bar":
        return (
          <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis 
              dataKey={xAxisKey} 
              stroke="#94a3b8" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false}
            />
            <YAxis 
              stroke="#94a3b8" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false}
            />
            <Tooltip 
              contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", color: "#f1f5f9" }}
              cursor={{ fill: "#334155", opacity: 0.4 }}
            />
            <Legend wrapperStyle={{ paddingTop: "10px" }} />
            {seriesKeys.map((key, index) => (
              <Bar 
                key={key} 
                dataKey={key} 
                fill={COLORS[index % COLORS.length]} 
                radius={[4, 4, 0, 0]} 
              />
            ))}
          </BarChart>
        );
      case "area":
        return (
          <AreaChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis 
              dataKey={xAxisKey} 
              stroke="#94a3b8" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false}
            />
            <YAxis 
              stroke="#94a3b8" 
              fontSize={12} 
              tickLine={false} 
              axisLine={false}
            />
            <Tooltip 
              contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", color: "#f1f5f9" }}
            />
            <Legend wrapperStyle={{ paddingTop: "10px" }} />
            {seriesKeys.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[index % COLORS.length]}
                fill={COLORS[index % COLORS.length]}
                fillOpacity={0.2}
              />
            ))}
          </AreaChart>
        );
      default:
        return null;
    }
  };

  return (
    <Card className="group/card w-full max-w-3xl my-6 overflow-hidden border-border-subtle bg-bg-secondary/40 backdrop-blur-md shadow-xl transition-all duration-300 hover:border-accent/20 hover:bg-bg-secondary/60">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-base font-bold tracking-tight text-text-primary">
          {title}
        </CardTitle>
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/5 text-accent/60 group-hover/card:bg-accent/10 group-hover/card:text-accent transition-all duration-300">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>
          </svg>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[320px] w-full pt-2">
          <ResponsiveContainer width="100%" height="100%">
            {renderChart() || <div className="flex items-center justify-center h-full text-text-secondary italic opacity-50">Unsupported Chart Type</div>}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};
