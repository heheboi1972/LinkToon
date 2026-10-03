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
  owner_id?: string;
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
  metadata: Record<string, unknown> & { filename?: string };
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

export interface CharacterSummary {
  id: string;
  project_id: string;
  name: string;
  description: string;
  appearance?: string;
  personality?: string;
  clothing?: string;
  prompt_token?: string;
  character_bible?: Record<string, unknown>;
  appearance_lock?: Record<string, unknown>;
  style_lock?: Record<string, unknown>;
  primary_asset_id?: string | null;
  reference_asset_id?: string | null;
  reference_media_url?: string | null;
  reference_stale?: boolean;
  character_revision?: number;
  reference_generated_from_revision?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface CharacterCreateInput {
  name: string;
  description?: string;
  appearance?: string;
  personality?: string;
  clothing?: string;
  age_range?: string;
  gender_presentation?: string;
  face_description?: string;
  hair_description?: string;
  eye_description?: string;
  body_description?: string;
  accessories_description?: string;
  visual_style?: string;
  appearance_lock?: Record<string, unknown>;
  style_lock?: Record<string, unknown>;
}

export type CharacterPatchInput = Partial<CharacterCreateInput>;

export interface CharacterReferenceGenerationOutput {
  character_id: string;
  reference_asset_id: string;
  asset_ids: string[];
  mock: boolean;
}

export interface StoryGenerationRequest {
  idea: string;
  genre?: string | null;
  tone?: string;
  theme?: string;
  characters?: string[];
  scene_count?: number;
}

export type GenerationJobStatus =
  | "queued"
  | "running"
  | "provider_pending"
  | "saving"
  | "succeeded"
  | "failed"
  | "canceled";

export interface StoryGenerationResponse {
  job_id: string;
  status: GenerationJobStatus;
}

export type ImageGenerationResponse = StoryGenerationResponse;

export interface SceneRecord {
  id: string;
  episode_id: string;
  position: number;
  title: string;
  image_asset_id: string | null;
  video_asset_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReaderDialogue {
  character: string;
  text: string;
}

export interface ReaderScene {
  id: string;
  order: number;
  title: string;
  narration: string;
  dialogue: ReaderDialogue[];
  image_url: string | null;
  video_url: string | null;
}

export interface EpisodeReader {
  episode_id: string;
  project_id: string;
  number: number;
  title: string;
  summary: string;
  scenes: ReaderScene[];
}

export type PublicationVisibility = "private" | "unlisted" | "public";
export interface Publication {
  id: string;
  project_id: string;
  episode_id: string;
  slug: string;
  title: string;
  description: string;
  visibility: PublicationVisibility;
  status: "published" | "unpublished";
  current_version: number;
  published_at: string | null;
  scene_count: number;
  image_count: number;
  motion_count: number;
}
export interface PublicationScene {
  order: number;
  title: string;
  narration: string;
  dialogue: ReaderDialogue[];
  image_url: string | null;
  video_url: string | null;
}
export interface PublicationReader {
  slug: string;
  title: string;
  description: string;
  author_name: string;
  published_at: string;
  visibility: "unlisted" | "public";
  scene_count: number;
  scenes: PublicationScene[];
}
export interface ProjectOverview {
  project_id: string;
  episode_count: number;
  scene_count: number;
  image_count: number;
  motion_count: number;
  character_count: number;
  character_reference_count: number;
  published_count: number;
  latest_scene_image_url: string | null;
  latest_scene_title: string | null;
  updated_at: string;
}

export interface SceneImageGenerationOutput {
  scene_id: string;
  asset_id: string;
  asset_ids: string[];
  mock: boolean;
}

export interface StoryDialogue {
  character_id: string | null;
  character: string;
  text: string;
}

export interface StoryScene {
  order: number;
  title: string;
  narration: string;
  dialogue: StoryDialogue[];
  visual_prompt: string;
  character_ids: string[];
}

export interface StoryGenerationOutput {
  title: string;
  synopsis: string;
  scenes: StoryScene[];
  episode_id: string;
  scene_ids: string[];
  asset_ids: string[];
  mock: boolean;
}

export interface GenerationJob {
  id: string;
  project_id: string;
  job_type: string;
  status: GenerationJobStatus;
  progress: number;
  retry_count: number;
  next_poll_at: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancel_requested_at: string | null;
  created_at: string;
  updated_at: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  cost_estimate: number | null;
  cost_actual: number | null;
}
