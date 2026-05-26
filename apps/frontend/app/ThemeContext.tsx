"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

// 1. Create the Context with default values
const ThemeContext = createContext({
  darkMode: true, // Defaulting to your dark hacker aesthetic
  toggleDarkMode: () => {},
});

// 2. Export the Provider to wrap the app in layout.tsx
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [darkMode, setDarkMode] = useState(true);

  // Safe side-effect: Updates the root HTML tag for Tailwind
  useEffect(() => {
    const root = window.document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
      root.style.colorScheme = "dark";
    } else {
      root.classList.remove("dark");
      root.style.colorScheme = "light";
    }
  }, [darkMode]);

  const toggleDarkMode = () => setDarkMode((prev) => !prev);

  return (
    <ThemeContext.Provider value={{ darkMode, toggleDarkMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

// 3. Export the hook for use in other components
export const useTheme = () => useContext(ThemeContext);