export const dynamic = "force-dynamic";
export async function GET() {
  return Response.json(
    {
      supabaseUrl:
        process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "",
      supabaseAnonKey:
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
        process.env.SUPABASE_ANON_KEY ||
        "",
      backendConfigured: Boolean(process.env.ASSISTANT_API_URL),
      localAuth:
        process.env.NODE_ENV === "development" &&
        process.env.LOCAL_DEMO_AUTH === "true",
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
