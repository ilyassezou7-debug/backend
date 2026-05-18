-- Create redirects table
CREATE TABLE redirects (
    id UUID NOT NULL,
    slug VARCHAR(255) NOT NULL,
    target_url TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id)
);

-- Create index on slug for fast lookups
CREATE UNIQUE INDEX ix_redirects_slug ON redirects (slug);

-- Update alembic version (if you are using alembic tracking)
-- INSERT INTO alembic_version (version_num) VALUES ('002_add_redirects');
