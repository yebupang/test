"use client";

interface Props {
  value: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}

export default function PnlBadge({ value, prefix = "", suffix = "%", className = "" }: Props) {
  const v = (value == null || !isFinite(value)) ? 0 : value;
  const isUp = v > 0;
  const isFlat = v === 0;
  const color = isFlat ? "text-gray-400" : isUp ? "text-up" : "text-down";
  const sign = isUp ? "+" : "";
  return (
    <span className={`font-mono text-sm ${color} ${className}`}>
      {sign}{prefix}{v.toFixed(2)}{suffix}
    </span>
  );
}
