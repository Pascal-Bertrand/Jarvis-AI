'use client'
import { SessionProvider } from 'next-auth/react'
 
/**
 * Wraps the application with the `SessionProvider` to enable session management.
 * @param {object} props - The component's props.
 * @param {React.ReactNode} props.children - The child components to render.
 * @returns {JSX.Element} The `SessionProvider` component wrapping the children.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>
} 