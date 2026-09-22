"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

import type { SipFrequency } from "@/types/fund";

interface InvestmentInputsValue {
  lumpsumInput: string;
  setLumpsumInput: (v: string) => void;
  sipInput: string;
  setSipInput: (v: string) => void;
  sipFrequency: SipFrequency;
  setSipFrequency: (v: SipFrequency) => void;
  lumpsum: number;
  sipAmount: number;
  hasLumpsum: boolean;
  hasSip: boolean;
}

const InvestmentContext = createContext<InvestmentInputsValue | null>(null);

/** Shares the lumpsum/SIP amount + frequency inputs between the compact
 * controls bar in the page header and the unified return cards further
 * down the page — two different places in the server-rendered tree that
 * both need the same live input state, so this wraps everything between
 * them rather than each holding its own separate copy. */
export function InvestmentProvider({ children }: { children: ReactNode }) {
  const [lumpsumInput, setLumpsumInput] = useState("");
  const [sipInput, setSipInput] = useState("");
  const [sipFrequency, setSipFrequency] = useState<SipFrequency>("monthly");

  const lumpsum = Number(lumpsumInput);
  const sipAmount = Number(sipInput);
  const hasLumpsum = lumpsumInput.trim() !== "" && lumpsum > 0;
  const hasSip = sipInput.trim() !== "" && sipAmount > 0;

  return (
    <InvestmentContext.Provider
      value={{
        lumpsumInput,
        setLumpsumInput,
        sipInput,
        setSipInput,
        sipFrequency,
        setSipFrequency,
        lumpsum,
        sipAmount,
        hasLumpsum,
        hasSip,
      }}
    >
      {children}
    </InvestmentContext.Provider>
  );
}

export function useInvestmentInputs(): InvestmentInputsValue {
  const ctx = useContext(InvestmentContext);
  if (!ctx) throw new Error("useInvestmentInputs must be used within an InvestmentProvider");
  return ctx;
}
