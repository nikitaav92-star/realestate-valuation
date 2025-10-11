"use client";
import { useRouter, useSearchParams } from "next/navigation";
import SearchBar from "@/components/SearchBar";
import { customHref } from "./utils";
import { Suspense } from "react";

function Search() {
  const router = useRouter();
  const searchParams = useSearchParams()

    // Function to handle search
    const handleSearch = (searchTerm: string) => {
    
      // Redirect to the search results page with the search term
      const searchQuery = new URLSearchParams();
      searchQuery.set('q', searchTerm);
      const resolvedHref = customHref(searchParams, `/listings/search`, searchQuery );
  
      router.push(resolvedHref);
    };
 
  return <SearchBar onSearch={handleSearch} />
}


export default function Main() {
 



  return (
<main>
    <div className="flex flex-col items-center justify-around bg-gradient-to-br from-blue-50 to-indigo-100 aspect-16/10">
      <div className="flex flex-col px-6 sm:pt-8 lg:px-0 ">
        <div className="flex flex-col gap-8 text-center">
          <p className="custom-title-1 font-inter text-indigo-900">
            CIAN Analytics
            </p>
          <p className="custom-title-2 font-inter text-gray-700">
            Аналитика недвижимости с AI оценкой состояния
          </p>
          <p className="text-sm text-gray-600">
            📊 100,000+ объявлений • 🤖 AI анализ фото • 📈 История цен
          </p>
        </div>

      </div>
      <div className="px-24 gap-2 pb-12 pt-12 w-2/3">
          <Suspense ><Search /></Suspense>
      </div>
      <div></div>
    </div>
    </main>

  )
}
