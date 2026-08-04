"use client";

import { useEffect, useState } from "react";

interface CountUpProps {
  value: number | undefined;
  duration?: number;
  format?: (val: number) => string;
}

export function CountUp({ value, duration = 300, format = (v) => v.toString() }: CountUpProps) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    if (value === undefined) return;

    const startValue = displayValue;
    const endValue = value;
    const startTime = performance.now();

    const updateValue = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // easeOutQuad
      const easeProgress = progress * (2 - progress);
      
      const current = startValue + (endValue - startValue) * easeProgress;
      setDisplayValue(current);

      if (progress < 1) {
        requestAnimationFrame(updateValue);
      } else {
        setDisplayValue(endValue);
      }
    };

    requestAnimationFrame(updateValue);
  }, [value, duration]);

  if (value === undefined) {
    return <span>—</span>;
  }

  // Handle floats vs ints correctly
  const finalValue = Number.isInteger(value) 
    ? Math.round(displayValue) 
    : Number(displayValue.toFixed(1));

  return <span>{format(finalValue)}</span>;
}
