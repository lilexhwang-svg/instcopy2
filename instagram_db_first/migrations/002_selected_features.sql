-- Run against an existing main database; preserves rows and can be repeated.
USE instagram_term_2026;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='users' AND column_name='bio'),
    'SELECT 1', 'ALTER TABLE users ADD COLUMN bio VARCHAR(300) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='users' AND column_name='avatar_path'),
    'SELECT 1', 'ALTER TABLE users ADD COLUMN avatar_path VARCHAR(255) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS comment_likes (
    user_id VARCHAR(32) NOT NULL,
    comment_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, comment_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (comment_id) REFERENCES comments(comment_id) ON DELETE CASCADE
) ENGINE=InnoDB;
