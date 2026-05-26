"use client";
import React, { createContext, useContext, useState } from "react";

// 1. Create the Context
const ThemeContext = createContext<any>(null);

// 2. Export the Provider to wrap the app in layout.tsx
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState("light");

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {/* This ensures the dark mode class is applied safely */}
      <div className={theme === "dark" ? "dark" : ""}>
        {children}
      </div>
    </ThemeContext.Provider>
  );
}

// 3. Export the hook so their layout.tsx doesn't crash
export const useTheme = () => useContext(ThemeContext);