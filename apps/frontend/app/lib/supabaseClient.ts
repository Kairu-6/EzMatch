import { createClient } from "@supabase/supabase-js";

// Single shared browser client. Reads public config from env (see .env.local).
// The anon key is subject to RLS — once policies are enabled, every query is
// scoped to the logged-in user's workspace by their session JWT.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
