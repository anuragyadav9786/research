"use client";

import { useEffect, useState } from "react";

const WORD_DOWN = "drops.";
const WORD_UP = "grows.";
const SWITCH_INTERVAL_MS = 4000;
const TYPE_SPEED_MS = 75;

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mql.matches);
    const listener = (e: MediaQueryListEvent) => setReduced(e.matches);
    mql.addEventListener("change", listener);
    return () => mql.removeEventListener("change", listener);
  }, []);

  return reduced;
}

export function AnimatedHeroHeadline({ centered = false }: { centered?: boolean }) {
  const reducedMotion = usePrefersReducedMotion();
  const [isUp, setIsUp] = useState(false);
  const [displayedText, setDisplayedText] = useState(WORD_DOWN);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    const targetWord = isUp ? WORD_UP : WORD_DOWN;

    if (reducedMotion) {
      setDisplayedText(targetWord);
      setIsTyping(false);
      const switchTimeout = setTimeout(() => setIsUp((prev) => !prev), SWITCH_INTERVAL_MS);
      return () => clearTimeout(switchTimeout);
    }

    let currentIndex = 0;
    setIsTyping(true);
    setDisplayedText("");

    const typeInterval = setInterval(() => {
      if (currentIndex <= targetWord.length) {
        setDisplayedText(targetWord.slice(0, currentIndex));
        currentIndex++;
      } else {
        clearInterval(typeInterval);
        setIsTyping(false);
      }
    }, TYPE_SPEED_MS);

    const switchTimeout = setTimeout(() => setIsUp((prev) => !prev), SWITCH_INTERVAL_MS);

    return () => {
      clearInterval(typeInterval);
      clearTimeout(switchTimeout);
    };
  }, [isUp, reducedMotion]);

  return (
    <h1
      className={`text-3xl sm:text-5xl font-semibold tracking-tight text-slate-100 text-balance leading-tight ${
        centered ? "text-center" : ""
      }`}
    >
      Know how your fund actually behaves{" "}
      <span
        className={`inline-flex items-center flex-wrap gap-x-3 gap-y-1 align-middle ${
          centered ? "justify-center" : ""
        }`}
      >
        <span>when the market</span>

        {/* Fixed-width container avoids layout shift as the word length changes. */}
        <span className="relative inline-flex items-center min-w-[110px] sm:min-w-[150px] text-left">
          <span
            className={`font-extrabold tracking-tight transition-colors duration-300 text-transparent bg-clip-text bg-gradient-to-r ${
              isUp ? "from-emerald-400 via-teal-300 to-emerald-200" : "from-rose-400 via-amber-300 to-rose-200"
            }`}
          >
            {displayedText}
          </span>

          {!reducedMotion && (
            <span
              className={`inline-block w-[2.5px] sm:w-[3.5px] h-[1em] ml-1 rounded-sm ${
                isUp ? "bg-emerald-400" : "bg-rose-400"
              } ${isTyping ? "opacity-100" : "animate-pulse"}`}
              aria-hidden="true"
            />
          )}
        </span>

        <span className="inline-flex items-center justify-center w-14 sm:w-20 h-6 sm:h-8 bg-slate-900/90 border border-slate-800 rounded-lg px-1.5 shadow-inner">
          {isUp ? (
            <svg key="sparkline-up" viewBox="0 0 80 28" className="w-full h-full overflow-visible" fill="none">
              <defs>
                <linearGradient id="bullGlow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(52 211 153)" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="rgb(52 211 153)" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              <path d="M 2 24 L 18 20 L 32 22 L 50 11 L 64 14 L 78 4 L 78 26 L 2 26 Z" fill="url(#bullGlow)" />
              <path
                d="M 2 24 L 18 20 L 32 22 L 50 11 L 64 14 L 78 4"
                stroke="rgb(52 211 153)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={
                  reducedMotion
                    ? { strokeDasharray: 100, strokeDashoffset: 0 }
                    : {
                        strokeDasharray: 100,
                        strokeDashoffset: 100,
                        animation: "hero-sparkline-dash 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards",
                      }
                }
              />
              {!reducedMotion && <circle cx="78" cy="4" r="2.5" fill="rgb(52 211 153)" className="animate-ping" />}
            </svg>
          ) : (
            <svg key="sparkline-down" viewBox="0 0 80 28" className="w-full h-full overflow-visible" fill="none">
              <defs>
                <linearGradient id="bearGlow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(251 113 133)" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="rgb(251 113 133)" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              <path d="M 2 4 L 20 6 L 36 22 L 52 24 L 66 15 L 78 17 L 78 26 L 2 26 Z" fill="url(#bearGlow)" />
              <path
                d="M 2 4 L 20 6 L 36 22 L 52 24 L 66 15 L 78 17"
                stroke="rgb(251 113 133)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={
                  reducedMotion
                    ? { strokeDasharray: 100, strokeDashoffset: 0 }
                    : {
                        strokeDasharray: 100,
                        strokeDashoffset: 100,
                        animation: "hero-sparkline-dash 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards",
                      }
                }
              />
              {!reducedMotion && <circle cx="36" cy="22" r="2.5" fill="rgb(251 113 133)" className="animate-ping" />}
            </svg>
          )}
        </span>
      </span>
    </h1>
  );
}
