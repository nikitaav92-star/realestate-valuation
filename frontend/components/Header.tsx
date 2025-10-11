'use client;'

import Link from "next/link";
import { LinkQP } from "@/components/LinkQP";
import Image from 'next/image';
import { Suspense } from "react";

interface HeaderProps {
  homepage?: boolean;
}

export default function Header({ homepage = false }: HeaderProps) {
  const headerClass = homepage ? "flex w-full justify-between items-center px-20 py-6 border-b border-indigo-200 bg-white shadow-sm" : "flex w-full justify-between items-center px-20 py-6 border-b border-gray-200 bg-white";
  return (
    <>
      <header className={headerClass}>
        <Suspense > <LinkQP href="/">
          <div className="flex items-center gap-3">
            <div className="text-3xl">🏠</div>
            <div>
              <p className="text-xl font-['Noto Sans'] leading-[normal] font-black text-indigo-900">CIAN Analytics</p>
              <p className="text-xs text-gray-500 font-medium">AI-powered недвижимость</p>
            </div>
          </div>
        </LinkQP></Suspense>


        <Link href="/analytics-ai" className="hover:opacity-80 transition-opacity">
          <div className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
            </svg>
            <span className="font-semibold">Аналитика</span>
          </div>
        </Link>

      </header>
    </>
  );
}
