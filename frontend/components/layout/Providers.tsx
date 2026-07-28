"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { consumeSessionFromUrl } from "@/lib/auth";

export function Providers({ children }: { children: React.ReactNode }) {
  // Runs during this component's first render — before any child mounts and so
  // before the session query fires. An effect would be too late: the first
  // /auth/session call would go out unauthenticated and bounce the user to
  // /login just as the token arrived.
  useState(consumeSessionFromUrl);

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 1000 * 30, // 30 seconds
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
