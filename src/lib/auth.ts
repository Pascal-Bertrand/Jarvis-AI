import { NextAuthOptions } from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'

console.log("GOOGLE_CLIENT_ID:", process.env.GOOGLE_CLIENT_ID); // For debugging
console.log("GOOGLE_CLIENT_SECRET:", process.env.GOOGLE_CLIENT_SECRET); // For debugging

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    async jwt({ token, user, account }) {
      // Persist the OAuth access_token to the token right after signin
      if (account) {
        token.accessToken = account.access_token
        token.userId = user.id
      }
      return token
    },
    async session({ session, token }) {
      // Send properties to the client
      session.accessToken = token.accessToken as string
      session.userId = token.userId as string
      return session
    },
  },
  pages: {
    signIn: '/auth/signin',
  },
} 