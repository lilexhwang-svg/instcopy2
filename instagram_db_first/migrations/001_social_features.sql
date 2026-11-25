USE instagram_term_2026;

-- Optional social features. Existing tables and rows are preserved.
CREATE TABLE IF NOT EXISTS likes (
    user_id VARCHAR(32) NOT NULL,
    post_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
    INDEX idx_likes_post (post_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS saved_posts (
    user_id VARCHAR(32) NOT NULL,
    post_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
    INDEX idx_saved_posts_post (post_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS hashtags (
    hashtag_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS post_hashtags (
    post_id BIGINT NOT NULL,
    hashtag_id BIGINT NOT NULL,
    PRIMARY KEY (post_id, hashtag_id),
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
    FOREIGN KEY (hashtag_id) REFERENCES hashtags(hashtag_id) ON DELETE CASCADE,
    INDEX idx_post_hashtags_tag (hashtag_id)
) ENGINE=InnoDB;
