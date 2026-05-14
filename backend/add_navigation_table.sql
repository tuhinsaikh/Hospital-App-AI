-- Migration: Add navigation_graphs table for indoor navigation/pathfinding
-- Run this against your PostgreSQL database

SET search_path TO hospital, public;

-- Navigation graphs table: stores the auto-extracted graph from floor plan images
CREATE TABLE IF NOT EXISTS navigation_graphs (
    id SERIAL PRIMARY KEY,
    floor_number INTEGER NOT NULL DEFAULT 1,
    floor_name VARCHAR(100),
    graph_data JSONB NOT NULL,          -- {nodes: [...], edges: [...]}
    image_path VARCHAR(500),            -- relative URL to the floor plan image
    image_width INTEGER,
    image_height INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Ensure one graph per floor (upsert-friendly)
CREATE UNIQUE INDEX IF NOT EXISTS idx_nav_floor ON navigation_graphs(floor_number);
