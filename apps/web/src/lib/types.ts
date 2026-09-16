export interface Profile {
  id: string;
  email: string;
  display_name: string;
}
export interface Session {
  access_token: string;
  user: Profile;
}
export interface PublicConfig {
  auth_mode: "local" | "supabase";
  mock_ai: boolean;
  phase: number;
  supabase_url: string;
  supabase_anon_key: string;
  max_upload_bytes: number;
}
export interface Project {
  id: string;
  title: string;
  description: string;
  genre: string;
  orientation: string;
  creation_mode: string;
  status: string;
  thumbnail_asset_id: string | null;
  created_at: string;
  updated_at: string;
}
export interface Episode {
  id: string;
  project_id: string;
  number: number;
  title: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}
export interface Panel {
  id: string;
  episode_id: string;
  position: number;
  title: string;
  description: string;
  dialogue: string;
  image_asset_id: string | null;
  status: string;
  updated_at: string;
}
export interface Asset {
  id: string;
  project_id: string;
  asset_type: string;
  mime_type: string;
  public_url: string | null;
  width: number | null;
  height: number | null;
  file_size: number;
  metadata: { filename?: string };
  upload_status: string;
}
export interface Job {
  id: string;
  project_id: string;
  job_type: string;
  status: string;
  progress: number;
  error_message: string | null;
  created_at: string;
}
