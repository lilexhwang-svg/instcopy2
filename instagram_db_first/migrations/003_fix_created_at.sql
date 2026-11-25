-- Adds created_at to likes / saved_posts tables that were created before it existed.
-- Safe to run repeatedly; keeps all rows.
USE instagram_term_2026;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='likes' AND column_name='created_at'),
    'SELECT 1', 'ALTER TABLE likes ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='saved_posts' AND column_name='created_at'),
    'SELECT 1', 'ALTER TABLE saved_posts ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
