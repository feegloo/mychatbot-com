-- Add metadata_json column to uploaded_files for EXIF/PDF/file metadata
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS metadata_json JSONB;
