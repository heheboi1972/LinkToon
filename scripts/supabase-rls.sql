-- Run after Alembic on a dedicated Supabase project (SQL Editor, postgres role).
-- All writes go through FastAPI, preserving ownership + asset validation invariants.
BEGIN;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'profiles','projects','project_bibles','characters','character_references',
    'episodes','scenes','panels','assets','motion_plans','motion_layers',
    'animations','generation_jobs','publish_versions','publications',
    'publication_snapshots','publication_scenes'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', table_name);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', table_name);
    IF table_name <> 'profiles' THEN
      EXECUTE format('GRANT SELECT ON public.%I TO authenticated', table_name);
    END IF;
  END LOOP;
END $$;

-- Never grant password_hash to the browser role.
GRANT SELECT (id, email, display_name, created_at, updated_at)
ON public.profiles TO authenticated;

DROP POLICY IF EXISTS profiles_owner_read ON public.profiles;
CREATE POLICY profiles_owner_read ON public.profiles FOR SELECT TO authenticated
USING (id = (SELECT auth.uid()));

DROP POLICY IF EXISTS projects_owner_read ON public.projects;
CREATE POLICY projects_owner_read ON public.projects FOR SELECT TO authenticated
USING (owner_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS assets_owner_read ON public.assets;
CREATE POLICY assets_owner_read ON public.assets FOR SELECT TO authenticated
USING (owner_id = (SELECT auth.uid()) AND EXISTS (
  SELECT 1 FROM public.projects p WHERE p.id = assets.project_id AND p.owner_id = (SELECT auth.uid())
));

DROP POLICY IF EXISTS jobs_owner_read ON public.generation_jobs;
CREATE POLICY jobs_owner_read ON public.generation_jobs FOR SELECT TO authenticated
USING (user_id = (SELECT auth.uid()) AND EXISTS (
  SELECT 1 FROM public.projects p WHERE p.id = generation_jobs.project_id
  AND p.owner_id = (SELECT auth.uid())
));

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['project_bibles','characters','episodes'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS owner_read ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING
       (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = %I.project_id
       AND p.owner_id = (SELECT auth.uid())))', table_name, table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['scenes','panels','publish_versions'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS owner_read ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING
       (EXISTS (SELECT 1 FROM public.episodes e JOIN public.projects p ON p.id = e.project_id
       WHERE e.id = %I.episode_id AND p.owner_id = (SELECT auth.uid())))', table_name, table_name);
  END LOOP;
  DROP POLICY IF EXISTS owner_read ON public.publications;
  CREATE POLICY owner_read ON public.publications FOR SELECT TO authenticated
  USING (owner_id = (SELECT auth.uid()));
  DROP POLICY IF EXISTS owner_read ON public.publication_snapshots;
  CREATE POLICY owner_read ON public.publication_snapshots FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.publications pub
    WHERE pub.id = publication_snapshots.publication_id AND pub.owner_id = (SELECT auth.uid())
  ));
  DROP POLICY IF EXISTS owner_read ON public.publication_scenes;
  CREATE POLICY owner_read ON public.publication_scenes FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.publication_snapshots snap
    JOIN public.publications pub ON pub.id = snap.publication_id
    WHERE snap.id = publication_scenes.snapshot_id AND pub.owner_id = (SELECT auth.uid())
  ));
  FOREACH table_name IN ARRAY ARRAY['motion_plans','motion_layers','animations'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS owner_read ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING
       (EXISTS (SELECT 1 FROM public.panels pn JOIN public.episodes e ON e.id = pn.episode_id
       JOIN public.projects p ON p.id = e.project_id WHERE pn.id = %I.panel_id
       AND p.owner_id = (SELECT auth.uid())))', table_name, table_name);
  END LOOP;
END $$;

DROP POLICY IF EXISTS owner_read ON public.character_references;
CREATE POLICY owner_read ON public.character_references FOR SELECT TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.characters c JOIN public.projects p ON p.id = c.project_id
  WHERE c.id = character_references.character_id AND p.owner_id = (SELECT auth.uid())
));

-- Object writes/reads use the backend service role after application validation.
-- Do not create a public bucket or broad storage.objects policies for this bucket.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('linktoon-private', 'linktoon-private', false, 10485760,
        ARRAY['image/png','image/jpeg','image/webp'])
ON CONFLICT (id) DO UPDATE SET public = false, file_size_limit = 104857600,
  allowed_mime_types = ARRAY['image/png','image/jpeg','image/webp','video/mp4'];

COMMIT;
