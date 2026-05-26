"use client";
<<<<<<< HEAD
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
=======

import React, { createContext, useContext, useState, useEffect } from "react";

const ThemeContext = createContext({
  darkMode: false,
  toggleDarkMode: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [darkMode, setDarkMode] = useState(true);

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
>>>>>>> d9a30e5da91220dc49be3e7d49e30037a4c39f58
    </ThemeContext.Provider>
  );
}

<<<<<<< HEAD
// 3. Export the hook so their layout.tsx doesn't crash
=======
>>>>>>> d9a30e5da91220dc49be3e7d49e30037a4c39f58
export const useTheme = () => useContext(ThemeContext);