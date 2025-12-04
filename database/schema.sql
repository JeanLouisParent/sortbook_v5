-- Ce script initialise la base de données et la table principale `books`.
-- Il est conçu pour être exécuté une seule fois.

-- Crée un schéma `book_data` pour isoler les tables du projet.
CREATE SCHEMA IF NOT EXISTS book_data;

-- Crée l'extension pour générer des UUIDs si elle n'existe pas.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Crée la table `books` pour stocker les informations sur les livres traités.
CREATE TABLE IF NOT EXISTS book_data.books (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Informations sur le fichier
    file_hash TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,

    -- Données extraites localement
    isbn TEXT,
    isbn_source TEXT, -- 'metadata' | 'content' | 'none'
    has_cover BOOLEAN DEFAULT FALSE,

    -- Décision finale
    choice_source TEXT, -- 'isbn' | 'metadata' | 'text' | 'cover' | 'unknown'
    final_author TEXT,
    final_title TEXT,

    -- Métadonnées de traitement
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'processed' | 'duplicate_hash' | 'duplicate_isbn' | 'failed'
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    processing_time_ms INTEGER,
    error_message TEXT,

    -- Données JSON brutes de chaque étape du pipeline
    json_extract_isbn JSONB,
    json_extract_metadata JSONB,
    json_extract_cover JSONB,
    json_n8n_response JSONB
);

-- Index pour accélérer les recherches courantes
CREATE INDEX IF NOT EXISTS idx_books_file_hash ON book_data.books(file_hash);
CREATE INDEX IF NOT EXISTS idx_books_isbn ON book_data.books(isbn);
CREATE INDEX IF NOT EXISTS idx_books_status ON book_data.books(status);

-- Commentaire sur la table pour plus de clarté
COMMENT ON TABLE book_data.books IS 'Table centrale pour le pipeline de traitement des EPUBs.';
COMMENT ON COLUMN book_data.books.file_hash IS 'SHA256 du fichier EPUB pour la détection de doublons exacts.';
COMMENT ON COLUMN book_data.books.status IS 'Statut du livre dans le pipeline de traitement.';
COMMENT ON COLUMN book_data.books.choice_source IS 'Indique quelle source a été utilisée pour déterminer le titre/auteur final.';
