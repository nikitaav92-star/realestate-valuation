UPDATE listings
SET is_active = FALSE
WHERE last_seen::DATE < NOW()::DATE;
